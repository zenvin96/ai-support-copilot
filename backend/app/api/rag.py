import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import current_user
from app.db.models import Document
from app.db.session import get_db
from app.schemas import DocTextIn, DocUpdateIn, RagQueryIn
from app.services.rag.ingest import delete_document, ingest_document, ingest_text
from app.services.rag.retriever import retrieve

router = APIRouter(prefix="/rag", tags=["rag"], dependencies=[Depends(current_user)])
ALLOWED = {".md", ".txt", ".pdf"}


@router.post("/documents")
async def upload(file: UploadFile, bg: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED:
        raise HTTPException(400, f"只支持 {', '.join(sorted(ALLOWED))}")
    updir = Path(get_settings().upload_dir)
    updir.mkdir(parents=True, exist_ok=True)
    path = updir / f"{uuid.uuid4().hex}{suffix}"
    path.write_bytes(await file.read())
    doc = Document(filename=file.filename)
    db.add(doc)
    await db.commit()
    bg.add_task(ingest_document, doc.id, path)
    return {"id": doc.id, "filename": doc.filename, "status": doc.status}


@router.get("/documents")
async def list_documents(db: AsyncSession = Depends(get_db)):
    rows = (await db.scalars(select(Document).order_by(Document.id.desc()))).all()
    return [{"id": d.id, "filename": d.filename, "chunk_count": d.chunk_count, "status": d.status,
             "error": d.error, "created_at": d.created_at} for d in rows]


@router.get("/documents/{doc_id}")
async def get_document(doc_id: int, db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404)
    return {"id": doc.id, "filename": doc.filename, "content": doc.content or "",
            "chunk_count": doc.chunk_count, "status": doc.status, "error": doc.error}


@router.post("/documents/text")
async def create_from_text(body: DocTextIn, bg: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    name = body.filename if body.filename.endswith((".md", ".txt")) else f"{body.filename}.md"
    doc = Document(filename=name, content=body.content)
    db.add(doc)
    await db.commit()
    bg.add_task(ingest_text, doc.id, body.content)
    return {"id": doc.id, "filename": doc.filename, "status": doc.status}


@router.put("/documents/{doc_id}")
async def update_document(doc_id: int, body: DocUpdateIn, bg: BackgroundTasks,
                          db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404)
    if body.filename:
        doc.filename = body.filename
    doc.content = body.content
    doc.status = "pending"
    await db.commit()
    bg.add_task(ingest_text, doc_id, body.content)
    return {"id": doc.id, "filename": doc.filename, "status": doc.status}


@router.delete("/documents/{doc_id}")
async def remove(doc_id: int, db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, doc_id, with_for_update=True)
    if not doc:
        raise HTTPException(404)
    await delete_document(doc_id)
    await db.delete(doc)
    await db.commit()
    return {"ok": True}


@router.post("/query")
async def query(body: RagQueryIn):
    return [c.to_dict() for c in await retrieve(body.query, body.top_k)]
