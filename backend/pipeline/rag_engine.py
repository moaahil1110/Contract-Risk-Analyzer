"""
RAG Engine Module (Week 2)
Handles ChromaDB vector store operations and benchmark retrieval.
Uses local ChromaDB (persisted to ./chroma_db) with sentence-transformers embeddings.
"""

import os
import json
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
CHROMA_PERSIST_PATH = os.getenv("CHROMA_PERSIST_PATH", "./chroma_db")
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


def build_benchmark_store(benchmark_dir: str = "benchmarks") -> Dict[str, Any]:
    """
    Build ChromaDB from all benchmark JSON files.
    
    Loads: nda_benchmarks.json, employment_benchmarks.json, vendor_benchmarks.json
    Creates embeddings using sentence-transformers
    Persists to ./chroma_db
    
    Returns:
        Dict with counts and status
    """
    benchmark_files = [
        "nda_benchmarks.json",
        "employment_benchmarks.json", 
        "vendor_benchmarks.json"
    ]
    
    collection = get_benchmark_collection()
    model = get_embedding_model()
    
    total_added = 0
    total_skipped = 0
    
    for filename in benchmark_files:
        filepath = Path(benchmark_dir) / filename
        if not filepath.exists():
            # Try with full path from project root
            filepath = Path(__file__).parent.parent / "benchmarks" / filename
        
        if not filepath.exists():
            logger.warning(f"Benchmark file not found: {filepath}")
            continue
        
        logger.info(f"Processing {filename}...")
        
        with open(filepath, "r") as f:
            benchmarks = json.load(f)
        
        contract_type = filename.replace("_benchmarks.json", "")
        
        # Prepare batch data
        ids = []
        texts = []
        metadatas = []
        
        for idx, benchmark in enumerate(benchmarks):
            benchmark_id = f"{contract_type}_{idx}"
            
            # Check if already exists
            try:
                existing = collection.get(ids=[benchmark_id], include=[])
                if existing and existing["ids"]:
                    total_skipped += 1
                    continue
            except Exception:
                pass
            
            # Combine text and risk notes for embedding
            text_to_embed = f"{benchmark.get('type', '')}: {benchmark.get('text', '')}"
            
            ids.append(benchmark_id)
            texts.append(text_to_embed)
            metadatas.append({
                "contract_type": contract_type,
                "clause_type": benchmark.get("type", "unknown"),
                "text": benchmark.get("text", ""),
                "risk_notes": benchmark.get("risk_notes", ""),
                "standard_version": benchmark.get("standard_version", ""),
            })
        
        # Batch add to collection
        if ids:
            embeddings = model.encode(texts, convert_to_numpy=True, batch_size=32)
            collection.add(
                ids=ids,
                embeddings=embeddings.tolist(),
                metadatas=metadatas,
            )
            total_added += len(ids)
            logger.info(f"  Added {len(ids)} benchmarks from {filename}")
    
    # Note: PersistentClient auto-persists, no explicit persist() needed
    
    result = {
        "status": "success",
        "added": total_added,
        "skipped": total_skipped,
        "total_in_db": collection.count(),
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
            benchmarks.append({
                "id": str(benchmark_id),
                "text": str(metadata.get("text", "")),
                "risk_notes": str(metadata.get("risk_notes", "")),
                "standard_version": str(metadata.get("standard_version", "")),
                "contract_type": str(metadata.get("contract_type", "")),
                "clause_type": str(metadata.get("clause_type", "")),
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
