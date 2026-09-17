"""文档加载 -> 切片 -> embedding -> 写入 Chroma。"""
import asyncio
import logging
import uuid
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import Document
from app.db.session import SessionLocal
from app.services.llm.service import llm_service
from app.services.rag.chroma import get_collection


def load_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        return "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
    return path.read_text(encoding="utf-8", errors="ignore")


def split_text(text: str, chunk_size: int | None = None, overlap: int | None = None) -> list[str]:
    s = get_settings()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size or s.chunk_size,
        chunk_overlap=overlap or s.chunk_overlap,
        separators=["\n## ", "\n### ", "\n\n", "\n", "。", ". ", " ", ""],
    )
    return [c.strip() for c in splitter.split_text(text) if c.strip()]


async def _reindex(doc_id: int, text: str) -> None:
    """Stage immutable chunks, then publish their version in one DB transaction."""
    version = uuid.uuid4().hex
    col = None
    async with SessionLocal() as db:
        doc = await db.get(Document, doc_id)
        if doc is None:
            return
        expected_content, filename = doc.content, doc.filename
        expected_version = doc.index_version
        if expected_content is not None and expected_content != text:
            return  # Superseded before this background task started.
    try:
        chunks = split_text(text)
        if not chunks:
            raise ValueError("文档为空或无法提取文本")
        embeddings: list = []
        for i in range(0, len(chunks), 64):
            embeddings += await llm_service.embed(chunks[i:i + 64])
        col = await asyncio.to_thread(get_collection)
        for start in range(0, len(chunks), 64):
            end = min(start + 64, len(chunks))
            await asyncio.to_thread(
                col.upsert,
                ids=[f"{doc_id}-{version}-{i}" for i in range(start, end)],
                documents=chunks[start:end], embeddings=embeddings[start:end],
                metadatas=[{"doc_id": doc_id, "filename": filename, "chunk_index": i,
                            "index_version": version} for i in range(start, end)],
            )
        async with SessionLocal() as db:
            doc = await db.get(Document, doc_id, with_for_update=True)
            if doc is None or doc.content != expected_content or doc.filename != filename:
                # A newer edit or deletion won while embeddings were being built.
                await asyncio.to_thread(col.delete, where={"index_version": version})
                return
            previous = doc.index_version
            doc.content, doc.chunk_count, doc.index_version = text, len(chunks), version
            doc.status, doc.error = "ready", None
            await db.commit()
    except Exception as e:
        # A lost commit acknowledgement may still mean publication succeeded.
        # Check MySQL before removing staged chunks; never delete an active version.
        async with SessionLocal() as db:
            doc = await db.get(Document, doc_id, with_for_update=True)
            if doc is not None and doc.index_version == version:
                return
            if (doc is not None and doc.content == expected_content and doc.filename == filename
                    and doc.index_version == expected_version):
                doc.status, doc.error = "failed", str(e)[:2000]
                await db.commit()
        if col is not None:
            try:
                await asyncio.to_thread(col.delete, where={"index_version": version})
            except Exception:
                logging.getLogger(__name__).exception("Failed to clean staged index %s", version)
        return
    # Publishing waits for readers of the old version. Cleanup failure is harmless:
    # retrieval only considers the version referenced by MySQL.
    try:
        await asyncio.to_thread(col.delete, where={"$and": [
            {"doc_id": doc_id}, {"index_version": previous}]})
    except Exception:
        logging.getLogger(__name__).exception("Failed to clean previous index for document %s", doc_id)


async def ingest_document(doc_id: int, path: Path) -> None:
    """上传文件入库：先抽取文本再走统一 reindex。"""
    try:
        text = await asyncio.to_thread(load_text, path)
    except Exception as e:  # noqa: BLE001
        async with SessionLocal() as db:
            doc = await db.get(Document, doc_id)
            if doc is not None and doc.content is None:
                doc.status, doc.error = "failed", str(e)[:2000]
                await db.commit()
        return
    await _reindex(doc_id, text)


async def ingest_text(doc_id: int, text: str) -> None:
    """从原文直接入库（新建/编辑保存时用）。"""
    await _reindex(doc_id, text)


async def delete_document(doc_id: int) -> None:
    col = get_collection()
    await asyncio.to_thread(col.delete, where={"doc_id": doc_id})


async def backfill_content() -> None:
    """给 content 为空的历史文档回填：用 Chroma 里的分片按 chunk_index 拼回原文。
    早期上传（content 列存在前）的文档因此也能在前端查看/编辑。"""
    col = get_collection()
    async with SessionLocal() as db:
        docs = (await db.scalars(select(Document))).all()
        for doc in docs:
            res = await asyncio.to_thread(col.get, where={"doc_id": doc.id},
                                          include=["documents", "metadatas"])
            # Migrate pre-versioning chunks before serving retrieval requests.
            if doc.index_version == "legacy":
                legacy = [(i, {**m, "index_version": "legacy"})
                          for i, m in zip(res["ids"], res["metadatas"]) if "index_version" not in m]
                for start in range(0, len(legacy), 64):
                    batch = legacy[start:start + 64]
                    await asyncio.to_thread(col.update, ids=[i for i, _ in batch],
                                            metadatas=[m for _, m in batch])
            if doc.content:
                continue
            pairs = sorted(((m, t) for m, t in zip(res["metadatas"], res["documents"])
                            if m.get("index_version", "legacy") == doc.index_version),
                           key=lambda x: x[0].get("chunk_index", 0))
            if pairs:
                doc.content = "\n\n".join(t for _, t in pairs)
        await db.commit()
