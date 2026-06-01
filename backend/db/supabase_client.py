"""
Supabase Client Module
Week 3: Supabase integration with PostgreSQL operations
"""

import os
import logging
from typing import Optional
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# Global Supabase client instance (initialized lazily)
_supabase_client: Optional[Client] = None


def get_supabase_client() -> Optional[Client]:
    """
    Get or create a Supabase client instance.
    Returns None if Supabase credentials are not configured.
    
    Returns:
        Supabase client instance or None
    """
    global _supabase_client
    
    if _supabase_client is not None:
        return _supabase_client
    
    # Load credentials from environment
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_service_key = os.getenv("SUPABASE_SERVICE_KEY")
    
    if not supabase_url or not supabase_service_key:
        logger.warning("Supabase credentials not configured. Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env")
        return None
    
    try:
        _supabase_client = create_client(supabase_url, supabase_service_key)
        logger.info("Supabase client initialized successfully")
        return _supabase_client
    except Exception as e:
        logger.error(f"Failed to initialize Supabase client: {e}")
        return None


def is_supabase_configured() -> bool:
    """
    Check if Supabase credentials are configured.
    
    Returns:
        True if Supabase is configured, False otherwise
    """
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_service_key = os.getenv("SUPABASE_SERVICE_KEY")
    return bool(supabase_url and supabase_service_key)


def reset_client():
    """
    Reset the Supabase client (useful for testing).
    """
    global _supabase_client
    _supabase_client = None
    logger.info("Supabase client reset")


# Export the client getter
__all__ = ["get_supabase_client", "is_supabase_configured", "reset_client"]
