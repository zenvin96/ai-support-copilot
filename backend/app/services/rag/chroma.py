import chromadb
from chromadb.api import ClientAPI

from app.core.config import get_settings

COLLECTION = "kb_default"
_client: ClientAPI | None = None


def get_client() -> ClientAPI:
    global _client
    if _client is None:
        s = get_settings()
        _client = chromadb.HttpClient(host=s.chroma_host, port=s.chroma_port)
    return _client


def get_collection():
    return get_client().get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})
