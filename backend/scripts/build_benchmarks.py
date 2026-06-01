#!/usr/bin/env python3
"""
Build Benchmarks Script (Week 2)
Standalone script to build ChromaDB vector store from benchmark JSON files.

Usage:
    python scripts/build_benchmarks.py
    python scripts/build_benchmarks.py --force  # Rebuild even if benchmarks exist
    python scripts/build_benchmarks.py --stats   # Show collection stats only
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# Add backend directory to path for imports
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from pipeline.rag_engine import (
    build_benchmark_store,
    get_collection_stats,
    get_benchmark_collection,
    get_chroma_client,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def show_stats():
    """Display current collection statistics."""
    try:
        stats = get_collection_stats()
        print("\n" + "=" * 50)
        print("ChromaDB Collection Statistics")
        print("=" * 50)
        print(f"Collection Name: {stats['collection_name']}")
        print(f"Total Benchmarks: {stats['total_benchmarks']}")
        print(f"Embedding Model: {stats['embedding_model']}")
        print(f"Persist Path: {stats['persist_path']}")
        print("=" * 50 + "\n")
        return stats
    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        return None


def clear_collection():
    """Clear the existing benchmark collection."""
    try:
        collection = get_benchmark_collection()
        count = collection.count()
        
        # Get all IDs
        if count > 0:
            all_data = collection.get(include=[])
            all_ids = all_data["ids"]
            collection.delete(ids=all_ids)
            # Note: PersistentClient auto-persists
            logger.info(f"Cleared {count} benchmarks from collection")
        else:
            logger.info("Collection is already empty")
        return True
    except Exception as e:
        logger.error(f"Failed to clear collection: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Build ChromaDB benchmark store for Contract Risk Analyzer"
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show collection statistics only (no build)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force rebuild by clearing existing data first",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear collection without rebuilding",
    )
    
    args = parser.parse_args()
    
    # Show stats only
    if args.stats:
        show_stats()
        return 0
    
    # Clear only
    if args.clear:
        if clear_collection():
            show_stats()
            return 0
        return 1
    
    # Show current stats before build
    print("\nBefore build:")
    before_stats = show_stats()
    
    # Clear if forced
    if args.force:
        print("\n⚠️  Force flag set - clearing existing benchmarks...")
        clear_collection()
    
    # Build the benchmark store
    print("\n🔨 Building benchmark store...")
    print("-" * 50)
    
    try:
        result = build_benchmark_store()
        
        if result["status"] == "success":
            print("\n✅ Build successful!")
            print(f"   Added: {result['added']} benchmarks")
            print(f"   Skipped: {result['skipped']} (already existed)")
            print(f"   Total in DB: {result['total_in_db']}")
        else:
            print("\n❌ Build failed")
            return 1
            
    except Exception as e:
        logger.error(f"Build failed: {e}")
        print(f"\n❌ Build failed: {e}")
        return 1
    
    # Show stats after build
    print("\nAfter build:")
    after_stats = show_stats()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
