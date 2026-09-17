"""检索：向量 top-k，返回带来源的 chunk。"""
import asyncio
from dataclasses import dataclass

from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import Document
from app.db.session import SessionLocal
from app.services.llm.service import llm_service
from app.services.rag.chroma import get_collection


@dataclass
class Citation:
    doc_id: int
    filename: str
    chunk_index: int
    score: float
    text: str

    def to_dict(self) -> dict:
        return {"doc_id": self.doc_id, "filename": self.filename, "chunk_index": self.chunk_index,
                "score": round(self.score, 4), "text": self.text}


async def retrieve(query: str, top_k: int | None = None) -> list[Citation]:
    k = top_k or get_settings().rag_top_k
    [qvec] = await llm_service.embed([query])
    col = await asyncio.to_thread(get_collection)
    async with SessionLocal() as db:
        # Shared locks keep the selected versions alive until the vector query finishes.
        docs = (await db.scalars(select(Document).where(Document.chunk_count > 0)
                                 .with_for_update(read=True))).all()
        if not docs:
            return []
        filters = [{"$and": [{"doc_id": d.id}, {"index_version": d.index_version}]} for d in docs]
        where = filters[0] if len(filters) == 1 else {"$or": filters}
        res = await asyncio.to_thread(col.query, query_embeddings=[qvec],
                                      n_results=min(k, sum(d.chunk_count for d in docs)), where=where,
                                      include=["documents", "metadatas", "distances"])
    out: list[Citation] = []
    for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
        out.append(Citation(doc_id=int(meta["doc_id"]), filename=meta["filename"],
                            chunk_index=int(meta["chunk_index"]), score=1 - dist, text=doc))
    return out


def format_context(cits: list[Citation]) -> str:
    return "\n\n".join(f"[{i + 1}] 来源: {c.filename}\n{c.text}" for i, c in enumerate(cits))
