"""Semantic memory for the digest using ChromaDB + sentence-transformers.

Stores every curated digest item as a vector and retrieves similar past stories
before each new curation run, giving the agent context about recent coverage.
"""
import hashlib
import logging
import os
from datetime import date, timedelta

import config

log = logging.getLogger("memory")

_COLLECTION_NAME = "digest_history"
_MODEL_NAME = "all-MiniLM-L6-v2"
_SIMILARITY_THRESHOLD = 0.60  # cosine similarity — above this means "too similar / already covered"

_client = None
_collection = None
_embedder = None


def _chroma_dir():
    return os.path.join(os.path.dirname(config.DB_PATH), "chroma")


def get_memory_db():
    """Return (client, collection) or (None, None) on any failure."""
    global _client, _collection
    if _client is not None:
        return _client, _collection
    if not config.MEMORY_ENABLED:
        return None, None
    try:
        import chromadb
        _client = chromadb.PersistentClient(path=_chroma_dir())
        _collection = _client.get_or_create_collection(
            name=_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        log.info("memory: chromadb opened at %s (%d items)", _chroma_dir(), _collection.count())
        return _client, _collection
    except Exception as exc:  # noqa: BLE001
        log.warning("memory: could not open chromadb: %s", exc)
        return None, None


def _get_embedder():
    global _embedder
    if _embedder is not None:
        return _embedder
    try:
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer(_MODEL_NAME)
        return _embedder
    except Exception as exc:  # noqa: BLE001
        log.warning("memory: could not load embedder: %s", exc)
        return None


def _item_id(url):
    return hashlib.sha1(url.encode()).hexdigest()[:16]


def _embed_text(item):
    # Curated items have "why"; raw candidates have "summary" — use whichever is available
    context = item.get("why") or item.get("summary") or ""
    title = item.get("title") or ""
    return f"{title}. {context}" if context else title


def _date_int(d=None):
    """Return date as YYYYMMDD integer (usable with ChromaDB $gte/$lte operators)."""
    if d is None:
        d = date.today()
    return int(d.strftime("%Y%m%d"))


def save_digest(digest_items):
    """Upsert digest items into ChromaDB. Returns True on success."""
    if not digest_items:
        return False
    _, collection = get_memory_db()
    if collection is None:
        return False
    embedder = _get_embedder()
    if embedder is None:
        return False
    try:
        today_int = _date_int()
        today_str = date.today().isoformat()
        texts = [_embed_text(item) for item in digest_items]
        embeddings = embedder.encode(texts).tolist()
        ids = [_item_id(item["url"]) for item in digest_items]
        metadatas = [
            {
                "title": item.get("title", ""),
                "source": item.get("source", ""),
                "url": item.get("url", ""),
                "why": item.get("why", ""),
                "date": today_str,        # ISO string for display
                "date_int": today_int,    # int for $gte/$lte filtering
            }
            for item in digest_items
        ]
        collection.upsert(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)
        log.info("memory: saved %d items to chromadb", len(digest_items))
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("memory: save_digest failed: %s", exc)
        return False


def find_similar(candidates, n=3):
    """Query ChromaDB for stories similar to each candidate from the past MEMORY_WINDOW_DAYS.

    Returns a formatted PT-BR context string for the system prompt, or None.
    """
    _, collection = get_memory_db()
    if collection is None:
        return None
    if collection.count() == 0:
        log.info("memory: collection empty — no historical context")
        return None
    embedder = _get_embedder()
    if embedder is None:
        return None
    try:
        cutoff_int = _date_int(date.today() - timedelta(days=config.MEMORY_WINDOW_DAYS))
        query_texts = [_embed_text(c) for c in candidates]
        n_results = min(n, collection.count())
        # Query without where filter to avoid ChromaDB limitation when filtered set < n_results;
        # date filtering is done in post-processing via date_int metadata.
        results = collection.query(
            query_embeddings=embedder.encode(query_texts).tolist(),
            n_results=n_results,
            include=["metadatas", "distances"],
        )
        # Collect unique items above the similarity threshold within the date window
        seen_ids = set()
        similar = []
        for metadatas_row, distances_row in zip(results["metadatas"], results["distances"]):
            for meta, dist in zip(metadatas_row, distances_row):
                if meta.get("date_int", 0) < cutoff_int:
                    continue
                similarity = 1.0 - dist  # chromadb cosine returns distance not similarity
                if similarity < _SIMILARITY_THRESHOLD:
                    continue
                uid = _item_id(meta.get("url", ""))
                if uid in seen_ids:
                    continue
                seen_ids.add(uid)
                similar.append(meta)

        if not similar:
            log.info("memory: no sufficiently similar historical items found")
            return None

        log.info("memory: injecting %d-item historical context", len(similar))
        return _format_context(similar)
    except Exception as exc:  # noqa: BLE001
        log.warning("memory: find_similar failed: %s", exc)
        return None


def _format_context(similar_items):
    """Format similar past items as a PT-BR context block for the Claude system prompt."""
    lines = []
    for item in similar_items:
        d = item.get("date", "?")
        source = item.get("source", "?")
        title = item.get("title", "?")
        why = item.get("why", "")
        line = f"- [{d}] ({source}) \"{title}\""
        if why:
            line += f" — Por que importou: {why}"
        lines.append(line)

    body = "\n".join(lines)
    return (
        f"HISTÓRICO RECENTE (últimos {config.MEMORY_WINDOW_DAYS} dias):\n"
        f"{body}\n\n"
        "Use esse histórico para:\n"
        "1. Evitar cobrir as mesmas histórias novamente.\n"
        "2. Enquadrar tópicos recorrentes como desdobramentos.\n"
        "3. Identificar saturação de tópico."
    )
