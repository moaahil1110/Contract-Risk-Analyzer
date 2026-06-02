"""
RAG Engine Module (Week 2)
Handles ChromaDB vector store operations and benchmark retrieval.
Uses local ChromaDB persisted under backend/chroma_db by default.
"""

import os
import json
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

from pipeline.benchmark_schema import (
    benchmark_dir,
    format_benchmark_for_embedding,
    load_benchmarks,
    validate_benchmarks,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
DEFAULT_CHROMA_PERSIST_PATH = Path(__file__).resolve().parent.parent / "chroma_db"
CHROMA_PERSIST_PATH = os.getenv("CHROMA_PERSIST_PATH", str(DEFAULT_CHROMA_PERSIST_PATH))
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
COLLECTION_NAME = "contract_benchmarks"

# Global instances (initialized on first use)
_chroma_client: Optional[chromadb.Client] = None
_embedding_model: Optional[SentenceTransformer] = None
_benchmark_collection: Optional[chromadb.Collection] = None


def get_embedding_model() -> SentenceTransformer:
    """Get or initialize the sentence-transformers embedding model."""
    global _embedding_model
    if _embedding_model is None:
        logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL)
        logger.info("Embedding model loaded successfully")
    return _embedding_model


def get_chroma_client():
    """Get or initialize the ChromaDB persistent client."""
    global _chroma_client
    if _chroma_client is None:
        logger.info(f"Initializing ChromaDB at: {CHROMA_PERSIST_PATH}")
        _chroma_client = chromadb.PersistentClient(
            path=CHROMA_PERSIST_PATH,
            settings=Settings(
                anonymized_telemetry=False,
            )
        )
    return _chroma_client


def get_benchmark_collection() -> chromadb.Collection:
    """Get or create the benchmark collection."""
    global _benchmark_collection
    if _benchmark_collection is None:
        client = get_chroma_client()
        try:
            _benchmark_collection = client.get_collection(name=COLLECTION_NAME)
            logger.info(f"Connected to existing collection: {COLLECTION_NAME}")
        except Exception:
            logger.info(f"Creating new collection: {COLLECTION_NAME}")
            _benchmark_collection = client.create_collection(
                name=COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
    return _benchmark_collection


def embed_text(text: str) -> List[float]:
    """Generate embedding for a single text."""
    model = get_embedding_model()
    embedding = model.encode(text, convert_to_numpy=True)
    return embedding.tolist()


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Generate embeddings for multiple texts (batch processing)."""
    model = get_embedding_model()
    embeddings = model.encode(texts, convert_to_numpy=True, batch_size=32)
    return embeddings.tolist()


def _metadata_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return json.dumps(value)


def _benchmark_metadata(benchmark: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "benchmark_id": benchmark["benchmark_id"],
        "contract_type": benchmark["contract_type"],
        "clause_type": benchmark["clause_type"],
        "risk_level": benchmark["risk_level"],
        "clause_text": benchmark["clause_text"],
        "text": benchmark["clause_text"],
        "risk_rule": benchmark["risk_rule"],
        "why_risky": benchmark["why_risky"],
        "risk_notes": benchmark["why_risky"],
        "safe_version": benchmark["safe_version"],
        "source_name": benchmark["source_name"],
        "source_type": benchmark["source_type"],
        "source_url": benchmark["source_url"],
        "source_license_note": benchmark["source_license_note"],
        "jurisdiction": benchmark["jurisdiction"],
        "tags": json.dumps(benchmark.get("tags", [])),
        "standard_version": benchmark["source_name"],
    }


def build_benchmark_store(benchmark_directory: Optional[str] = None) -> Dict[str, Any]:
    """
    Build ChromaDB from all benchmark JSON files.
    
    Loads: nda_benchmarks.json, employment_benchmarks.json, vendor_benchmarks.json
    Creates embeddings using sentence-transformers
    Persists to ./chroma_db
    
    Returns:
        Dict with counts and status
    """
    directory = Path(benchmark_directory) if benchmark_directory else benchmark_dir()
    benchmarks = load_benchmarks(directory)
    validation_errors, validation_summary = validate_benchmarks(benchmarks)
    if validation_errors:
        raise ValueError("Benchmark schema validation failed: " + "; ".join(validation_errors[:10]))

    collection = get_benchmark_collection()
    model = get_embedding_model()

    total_added = 0
    total_skipped = 0

    ids = []
    texts = []
    metadatas = []

    for benchmark in benchmarks:
        benchmark_id = benchmark["benchmark_id"]

        try:
            existing = collection.get(ids=[benchmark_id], include=[])
            if existing and existing["ids"]:
                total_skipped += 1
                continue
        except Exception:
            pass

        ids.append(benchmark_id)
        texts.append(format_benchmark_for_embedding(benchmark))
        metadatas.append({
            key: _metadata_value(value)
            for key, value in _benchmark_metadata(benchmark).items()
        })

    for start in range(0, len(ids), 128):
        batch_ids = ids[start:start + 128]
        if not batch_ids:
            continue

        batch_texts = texts[start:start + 128]
        embeddings = model.encode(batch_texts, convert_to_numpy=True, batch_size=32)
        collection.add(
            ids=batch_ids,
            embeddings=embeddings.tolist(),
            metadatas=metadatas[start:start + 128],
        )
        total_added += len(batch_ids)
        logger.info("Added %s benchmark entries", len(batch_ids))

    # Note: PersistentClient auto-persists, no explicit persist() needed

    result = {
        "status": "success",
        "added": total_added,
        "skipped": total_skipped,
        "total_in_db": collection.count(),
        "schema": validation_summary,
    }
    logger.info(f"Benchmark store built: {result}")
    return result


def _format_query_results(results: Dict[str, Any]) -> List[Dict[str, Any]]:
    benchmarks = []
    if results and results["metadatas"] and results["metadatas"][0]:
        ids = results.get("ids", [[]])[0]
        for benchmark_id, metadata, distance in zip(ids, results["metadatas"][0], results["distances"][0]):
            # Convert distance (0-2 for cosine, where 0=identical) to similarity (0-1)
            similarity = 1 - (distance / 2) if distance <= 2 else 0
            tags = metadata.get("tags", "[]")
            if isinstance(tags, str):
                try:
                    tags = json.loads(tags)
                except json.JSONDecodeError:
                    tags = [tags] if tags else []
            benchmarks.append({
                "id": str(benchmark_id),
                "benchmark_id": str(metadata.get("benchmark_id") or benchmark_id),
                "text": str(metadata.get("text", "")),
                "clause_text": str(metadata.get("clause_text", metadata.get("text", ""))),
                "risk_level": str(metadata.get("risk_level", "")),
                "risk_rule": str(metadata.get("risk_rule", "")),
                "why_risky": str(metadata.get("why_risky", metadata.get("risk_notes", ""))),
                "risk_notes": str(metadata.get("risk_notes", "")),
                "safe_version": str(metadata.get("safe_version", "")),
                "standard_version": str(metadata.get("standard_version", "")),
                "contract_type": str(metadata.get("contract_type", "")),
                "clause_type": str(metadata.get("clause_type", "")),
                "source_name": str(metadata.get("source_name", "")),
                "source_type": str(metadata.get("source_type", "")),
                "source_url": str(metadata.get("source_url", "")),
                "source_license_note": str(metadata.get("source_license_note", "")),
                "jurisdiction": str(metadata.get("jurisdiction", "")),
                "tags": tags,
                "similarity": round(similarity, 4),
            })
    return benchmarks


def retrieve_benchmarks(clause_text: str, k: int = 3, contract_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Retrieve top-k similar benchmarks for a given clause.
    
    Args:
        clause_text: The clause text to search against
        k: Number of similar benchmarks to retrieve (default: 3)
        contract_type: Optional contract type filter (nda, employment, vendor)
    
    Returns:
        List of benchmark dicts with text, risk_notes, standard_version, and similarity score
    """
    collection = get_benchmark_collection()
    
    # Generate embedding for the clause
    query_embedding = embed_text(clause_text)
    
    normalized_type = (contract_type or "").lower()
    should_filter = normalized_type in {"nda", "employment", "vendor"}

    if should_filter:
        try:
            filtered_results = collection.query(
                query_embeddings=[query_embedding],
                n_results=k,
                where={"contract_type": normalized_type},
                include=["metadatas", "distances"],
            )
            benchmarks = _format_query_results(filtered_results)
            if len(benchmarks) >= k:
                logger.info(f"Retrieved {len(benchmarks)} {normalized_type} benchmarks for clause")
                return benchmarks
            logger.info(
                "Filtered retrieval returned %s/%s benchmarks for %s; falling back to broad retrieval",
                len(benchmarks),
                k,
                normalized_type,
            )
        except Exception as e:
            logger.warning(f"Filtered retrieval failed for {normalized_type}: {e}")
    
    # Broad fallback query.
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=k,
        include=["metadatas", "distances"],
    )
    benchmarks = _format_query_results(results)
    
    logger.info(f"Retrieved {len(benchmarks)} benchmarks for clause")
    return benchmarks


def get_collection_stats() -> Dict[str, Any]:
    """Get statistics about the benchmark collection."""
    collection = get_benchmark_collection()
    return {
        "collection_name": COLLECTION_NAME,
        "total_benchmarks": collection.count(),
        "persist_path": CHROMA_PERSIST_PATH,
        "embedding_model": EMBEDDING_MODEL,
    }


def init_engine():
    """Initialize the RAG engine (called at app startup)."""
    logger.info("RAG Engine initializing...")
    get_embedding_model()
    get_chroma_client()
    get_benchmark_collection()
    logger.info("RAG Engine initialized successfully")


# For testing as standalone
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Build the benchmark store
    result = build_benchmark_store()
    print(f"\nBuild result: {json.dumps(result, indent=2)}")
    
    # Test retrieval
    test_clause = "Employee agrees to hold all confidential information in strict confidence"
    benchmarks = retrieve_benchmarks(test_clause, k=3)
    print(f"\nRetrieved benchmarks for test clause:")
    for b in benchmarks:
        print(f"  - {b['clause_type']} (similarity: {b['similarity']})")
        print(f"    Risk: {b['risk_notes'][:100]}...")
