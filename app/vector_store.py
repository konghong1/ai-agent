"""
Vector Store Abstraction Layer
==============================

Provides a unified interface for multiple vector database backends.
Currently supports:
  - ChromaDB (default, local persistent)
  - FAISS (in-memory + file persistence)
  - Milvus (remote, requires milvus server)

Configuration via environment variables:
  VECTOR_STORE_BACKEND = "chroma" | "faiss" | "milvus"
  VECTOR_STORE_PATH    = "/path/to/vector_db"
  MILVUS_HOST          = "localhost"
  MILVUS_PORT          = 19530

Usage:
    from app.vector_store import get_vector_store
    vs = get_vector_store()
    vs.upsert("kb_1", ids=[...], embeddings=[...], documents=[...], metadatas=[...])
    results = vs.query("kb_1", query_embeddings=[...], n_results=10, where={...})
"""

from __future__ import annotations

import json
import logging
import os
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import numpy as np

from app.settings import get_settings

logger = logging.getLogger(__name__)

# Default RAG configuration applied to new knowledge bases
DEFAULT_RAG_CONFIG: dict[str, Any] = {
    "retrieval_strategy": "hybrid",      # "vector" | "keyword" | "hybrid"
    "top_k": 20,
    "rerank_top_k": 10,
    "mmr_enabled": True,
    "mmr_threshold": 0.5,
    "rerank_enabled": True,
    "rerank_model": "BAAI/bge-reranker-base",
    "min_relevance_score": 0.3,
    "rrf_k": 60,
}


# ============================================================
# Abstract Base Interface
# ============================================================

class VectorStoreBackend(ABC):
    """Abstract interface for vector store backends."""

    @abstractmethod
    def upsert(
        self,
        collection_name: str,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict],
    ) -> None:
        """Insert or update vectors."""
        ...

    @abstractmethod
    def query(
        self,
        collection_name: str,
        query_embeddings: list[list[float]],
        n_results: int = 10,
        where: dict | None = None,
    ) -> dict[str, Any]:
        """Search for similar vectors.

        Returns a dict with keys:
          - ids: list[list[str]]  (one list per query)
          - distances: list[list[float]]
          - documents: list[list[str]]
          - metadatas: list[list[dict]]
        """
        ...

    @abstractmethod
    def delete(self, collection_name: str, ids: list[str]) -> None:
        """Delete vectors by ID."""
        ...

    @abstractmethod
    def delete_collection(self, collection_name: str) -> None:
        """Delete an entire collection."""
        ...

    @abstractmethod
    def collection_exists(self, collection_name: str) -> bool:
        """Check if a collection exists."""
        ...

    @abstractmethod
    def ensure_collection(self, collection_name: str) -> None:
        """Get or create a collection."""
        ...


# ============================================================
# ChromaDB Backend (default)
# ============================================================

class ChromaBackend(VectorStoreBackend):
    """ChromaDB persistent client backend."""

    def __init__(self, path: str):
        import chromadb
        self._client = chromadb.PersistentClient(path=path)
        self._path = path
        logger.info("ChromaDB backend initialized at %s", path)

    def upsert(self, collection_name, ids, embeddings, documents, metadatas):
        coll = self._client.get_or_create_collection(collection_name)
        coll.upsert(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)

    def query(self, collection_name, query_embeddings, n_results=10, where=None):
        try:
            coll = self._client.get_collection(collection_name)
        except Exception:
            return {"ids": [[]], "distances": [[]], "documents": [[]], "metadatas": [[]]}
        kwargs: dict[str, Any] = {
            "query_embeddings": query_embeddings,
            "n_results": n_results,
            "include": ["metadatas", "distances", "documents"],
        }
        if where:
            kwargs["where"] = where
        results = coll.query(**kwargs)
        # Ensure all keys exist
        for key in ("ids", "distances", "documents", "metadatas"):
            if key not in results:
                results[key] = [[]]
        return results

    def delete(self, collection_name, ids):
        try:
            coll = self._client.get_collection(collection_name)
            coll.delete(ids=ids)
        except Exception:
            pass

    def delete_collection(self, collection_name):
        try:
            self._client.delete_collection(collection_name)
        except Exception:
            pass

    def collection_exists(self, collection_name):
        try:
            self._client.get_collection(collection_name)
            return True
        except Exception:
            return False

    def ensure_collection(self, collection_name):
        self._client.get_or_create_collection(collection_name)


# ============================================================
# FAISS Backend (in-memory + file persistence)
# ============================================================

class FAISSBackend(VectorStoreBackend):
    """FAISS backend with file-based persistence.

    Stores each collection as a .faiss index file + a .json metadata file.
    Suitable for smaller datasets and single-node deployments.
    """

    def __init__(self, path: str):
        self._path = Path(path)
        self._path.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()
        # Collection cache: name → {embeddings: np.ndarray, ids: list, documents: list, metadatas: list, dim: int}
        self._cache: dict[str, dict] = {}
        logger.info("FAISS backend initialized at %s", path)

    def _lock_for(self, name: str) -> threading.Lock:
        with self._global_lock:
            if name not in self._locks:
                self._locks[name] = threading.Lock()
            return self._locks[name]

    def _collection_files(self, name: str) -> tuple[Path, Path]:
        safe = name.replace("/", "_")
        return (self._path / f"{safe}.index", self._path / f"{safe}.json")

    def _load_collection(self, name: str) -> dict:
        if name in self._cache:
            return self._cache[name]
        idx_file, meta_file = self._collection_files(name)
        coll = {"embeddings": None, "ids": [], "documents": [], "metadatas": [], "dim": 0}
        if meta_file.exists():
            try:
                data = json.loads(meta_file.read_text(encoding="utf-8"))
                coll["ids"] = data.get("ids", [])
                coll["documents"] = data.get("documents", [])
                coll["metadatas"] = data.get("metadatas", [])
                coll["dim"] = data.get("dim", 0)
                if coll["dim"] > 0 and len(coll["ids"]) > 0:
                    coll["embeddings"] = np.zeros((len(coll["ids"]), coll["dim"]), dtype="float32")
                    if idx_file.exists():
                        import faiss
                        index = faiss.read_index(str(idx_file))
                        coll["embeddings"] = faiss.rev_swig_ptr(index.get_xb(), index.ntotal * coll["dim"])
                        coll["embeddings"] = coll["embeddings"].reshape(-1, coll["dim"]).copy()
            except Exception as exc:
                logger.warning("FAISS load collection %s failed: %s", name, exc)
        self._cache[name] = coll
        return coll

    def _save_collection(self, name: str, coll: dict) -> None:
        idx_file, meta_file = self._collection_files(name)
        try:
            if coll["embeddings"] is not None and len(coll["ids"]) > 0 and coll["dim"] > 0:
                import faiss
                index = faiss.IndexFlatIP(coll["dim"])
                index.add(coll["embeddings"].astype("float32"))
                faiss.write_index(index, str(idx_file))
            meta_file.write_text(json.dumps({
                "ids": coll["ids"],
                "documents": coll["documents"],
                "metadatas": coll["metadatas"],
                "dim": coll["dim"],
            }, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            logger.warning("FAISS save collection %s failed: %s", name, exc)

    def upsert(self, collection_name, ids, embeddings, documents, metadatas):
        with self._lock_for(collection_name):
            coll = self._load_collection(collection_name)
            if embeddings:
                dim = len(embeddings[0])
                if coll["dim"] == 0:
                    coll["dim"] = dim
                new_emb = np.array(embeddings, dtype="float32")
                for i, vid in enumerate(ids):
                    if vid in coll["ids"]:
                        idx = coll["ids"].index(vid)
                        coll["documents"][idx] = documents[i]
                        coll["metadatas"][idx] = metadatas[i]
                        if coll["embeddings"] is not None:
                            coll["embeddings"][idx] = new_emb[i]
                    else:
                        coll["ids"].append(vid)
                        coll["documents"].append(documents[i])
                        coll["metadatas"].append(metadatas[i])
                        if coll["embeddings"] is None:
                            coll["embeddings"] = new_emb[i:i+1].copy()
                        else:
                            coll["embeddings"] = np.vstack([coll["embeddings"], new_emb[i:i+1]])
                self._save_collection(collection_name, coll)

    def query(self, collection_name, query_embeddings, n_results=10, where=None):
        with self._lock_for(collection_name):
            coll = self._load_collection(collection_name)
        if not coll["ids"] or coll["embeddings"] is None:
            return {"ids": [[]], "distances": [[]], "documents": [[]], "metadatas": [[]]}

        query_vec = np.array(query_embeddings, dtype="float32")
        # Cosine similarity via normalized dot product
        norms = np.linalg.norm(coll["embeddings"], axis=1, keepdims=True)
        norms[norms == 0] = 1
        normalized = coll["embeddings"] / norms
        query_norms = np.linalg.norm(query_vec, axis=1, keepdims=True)
        query_norms[query_norms == 0] = 1
        normalized_query = query_vec / query_norms

        all_ids, all_distances, all_documents, all_metadatas = [], [], [], []
        for qi in range(len(query_embeddings)):
            sims = normalized_query[qi] @ normalized.T  # cosine similarity
            # Apply metadata filter
            valid_indices = list(range(len(coll["ids"])))
            if where:
                valid_indices = [
                    i for i in valid_indices
                    if all(
                        str(coll["metadatas"][i].get(k)) == str(v)
                        for k, v in where.items()
                    )
                ]
            if not valid_indices:
                all_ids.append([])
                all_distances.append([])
                all_documents.append([])
                all_metadatas.append([])
                continue
            valid_sims = [(sims[i], i) for i in valid_indices]
            valid_sims.sort(key=lambda x: -x[0])
            top = valid_sims[:n_results]
            all_ids.append([coll["ids"][i] for _, i in top])
            all_distances.append([1.0 - s for s, _ in top])  # distance = 1 - similarity
            all_documents.append([coll["documents"][i] for _, i in top])
            all_metadatas.append([coll["metadatas"][i] for _, i in top])

        return {
            "ids": all_ids,
            "distances": all_distances,
            "documents": all_documents,
            "metadatas": all_metadatas,
        }

    def delete(self, collection_name, ids):
        with self._lock_for(collection_name):
            coll = self._load_collection(collection_name)
            id_set = set(ids)
            keep_indices = [i for i, vid in enumerate(coll["ids"]) if vid not in id_set]
            coll["ids"] = [coll["ids"][i] for i in keep_indices]
            coll["documents"] = [coll["documents"][i] for i in keep_indices]
            coll["metadatas"] = [coll["metadatas"][i] for i in keep_indices]
            if coll["embeddings"] is not None and keep_indices:
                coll["embeddings"] = coll["embeddings"][keep_indices]
            elif not keep_indices:
                coll["embeddings"] = None
            self._save_collection(collection_name, coll)

    def delete_collection(self, collection_name):
        with self._lock_for(collection_name):
            idx_file, meta_file = self._collection_files(collection_name)
            idx_file.unlink(missing_ok=True)
            meta_file.unlink(missing_ok=True)
            self._cache.pop(collection_name, None)

    def collection_exists(self, collection_name):
        _, meta_file = self._collection_files(collection_name)
        return meta_file.exists()

    def ensure_collection(self, collection_name):
        self._load_collection(collection_name)


# ============================================================
# Milvus Backend (remote)
# ============================================================

class MilvusBackend(VectorStoreBackend):
    """Milvus backend for production-scale deployments.

    Requires a running Milvus server. Uses pymilvus SDK.
    """

    def __init__(self, host: str, port: int, prefix: str = "kb_"):
        from pymilvus import connections, utility
        self._prefix = prefix
        self._host = host
        self._port = port
        connections.connect(alias="default", host=host, port=str(port))
        logger.info("Milvus backend connected to %s:%s", host, port)

    def _coll_name(self, name: str) -> str:
        return name if name.startswith(self._prefix) else f"{self._prefix}{name.lstrip('kb_')}"

    def upsert(self, collection_name, ids, embeddings, documents, metadatas):
        from pymilvus import Collection, CollectionSchema, FieldSchema, DataType, utility
        name = self._coll_name(collection_name)
        dim = len(embeddings[0]) if embeddings else 0
        if dim == 0:
            return
        if not utility.has_collection(name):
            fields = [
                FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=200, is_primary=True),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dim),
                FieldSchema(name="document", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="metadata", dtype=DataType.VARCHAR, max_length=65535),
            ]
            schema = CollectionSchema(fields, enable_dynamic_field=True)
            coll = Collection(name, schema)
            coll.create_index("embedding", {"index_type": "IVF_FLAT", "metric_type": "IP", "params": {"nlist": 128}})
        else:
            coll = Collection(name)
        coll.insert([
            ids,
            embeddings,
            documents,
            [json.dumps(m, ensure_ascii=False) for m in metadatas],
        ])
        coll.flush()

    def query(self, collection_name, query_embeddings, n_results=10, where=None):
        from pymilvus import Collection, utility
        name = self._coll_name(collection_name)
        if not utility.has_collection(name):
            return {"ids": [[]], "distances": [[]], "documents": [[]], "metadatas": [[]]}
        coll = Collection(name)
        coll.load()
        all_ids, all_distances, all_documents, all_metadatas = [], [], [], []
        for qe in query_embeddings:
            expr_parts = []
            if where:
                for k, v in where.items():
                    expr_parts.append(f'{k} == "{v}"')
            expr = " and ".join(expr_parts) if expr_parts else None
            search_params = {"metric_type": "IP", "params": {"nprobe": 10}}
            results = coll.search(
                data=[qe], anns_field="embedding", param=search_params,
                limit=n_results, expr=expr,
                output_fields=["document", "metadata"],
            )
            ids, distances, docs, metas = [], [], [], []
            for hit in results[0]:
                ids.append(hit.id)
                distances.append(1.0 - hit.score)
                entity = hit.entity.get("document", "")
                docs.append(entity)
                meta_str = hit.entity.get("metadata", "{}")
                try:
                    metas.append(json.loads(meta_str))
                except Exception:
                    metas.append({})
            all_ids.append(ids)
            all_distances.append(distances)
            all_documents.append(docs)
            all_metadatas.append(metas)
        return {"ids": all_ids, "distances": all_distances, "documents": all_documents, "metadatas": all_metadatas}

    def delete(self, collection_name, ids):
        from pymilvus import Collection, utility
        name = self._coll_name(collection_name)
        if not utility.has_collection(name):
            return
        coll = Collection(name)
        expr = f'id in {ids}'
        coll.delete(expr)
        coll.flush()

    def delete_collection(self, collection_name):
        from pymilvus import utility
        name = self._coll_name(collection_name)
        if utility.has_collection(name):
            utility.drop_collection(name)

    def collection_exists(self, collection_name):
        from pymilvus import utility
        return utility.has_collection(self._coll_name(collection_name))

    def ensure_collection(self, collection_name):
        from pymilvus import Collection, CollectionSchema, FieldSchema, DataType, utility
        name = self._coll_name(collection_name)
        if not utility.has_collection(name):
            # Create with a default dimension — will be set on first upsert
            fields = [
                FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=200, is_primary=True),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=1536),
                FieldSchema(name="document", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="metadata", dtype=DataType.VARCHAR, max_length=65535),
            ]
            schema = CollectionSchema(fields, enable_dynamic_field=True)
            Collection(name, schema)


# ============================================================
# Factory — Singleton
# ============================================================

_store_instance: VectorStoreBackend | None = None
_store_lock = threading.Lock()


def get_vector_store() -> VectorStoreBackend:
    """Get the configured vector store backend singleton."""
    global _store_instance
    if _store_instance is None:
        with _store_lock:
            if _store_instance is None:
                settings = get_settings()
                backend = settings.vector_store_backend.lower().strip()
                path = settings.vector_store_path

                if backend == "chroma":
                    _store_instance = ChromaBackend(path)
                elif backend == "faiss":
                    _store_instance = FAISSBackend(path)
                elif backend == "milvus":
                    _store_instance = MilvusBackend(
                        host=settings.milvus_host,
                        port=settings.milvus_port,
                        prefix=settings.milvus_collection_prefix,
                    )
                else:
                    logger.warning("Unknown vector store backend '%s', falling back to chroma", backend)
                    _store_instance = ChromaBackend(path)

                logger.info("Vector store backend: %s", backend)
    return _store_instance
