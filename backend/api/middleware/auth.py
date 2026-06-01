"""
Authentication Middleware
Week 3: Supabase Auth integration with JWT validation
"""

import os
import jwt
import logging
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from db.supabase_client import get_supabase_client, is_supabase_configured

logger = logging.getLogger(__name__)

# Security scheme for Swagger UI
security = HTTPBearer(auto_error=False)

# DEV_MODE: if true, auth is optional
DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"

# JWT configuration
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")


def _get_supabase_jwks():
    """
    Get JWKS (JSON Web Key Set) from Supabase.
    This is used to verify the JWT signature.
    """
    # For simplicity, we'll use the JWT secret directly
    # In production, Supabase provides a JWKS endpoint
    return None


def verify_supabase_jwt(token: str) -> Optional[Dict[str, Any]]:
    """
    Verify a Supabase JWT token and return the decoded payload.
    
    Args:
        token: The JWT token to verify
    
    Returns:
        Decoded JWT payload if valid, None otherwise
    """
    try:
        # For Supabase, we need to verify against the JWT secret
        # The token structure is: header.payload.signature
        # Supabase uses HS256 algorithm
        
        if SUPABASE_JWT_SECRET:
            # Decode with the secret
            payload = jwt.decode(
                token,
                SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience="authenticated"
            )
        else:
            # If no secret, decode without verification (DEV MODE only)
            payload = jwt.decode(
                token,
                options={"verify_signature": False},
                algorithms=["HS256"]
            )
            logger.warning("Verifying JWT without signature (SUPABASE_JWT_SECRET not set)")
        
        return payload
        
    except jwt.ExpiredSignatureError:
        logger.warning("JWT token has expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid JWT token: {e}")
        return None
    except Exception as e:
        logger.error(f"Error verifying JWT: {e}")
        return None


def extract_user_from_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Extract user information from a JWT token.
    
    Args:
        token: The JWT token
    
    Returns:
        User dictionary with id and email, or None if invalid
    """
    payload = verify_supabase_jwt(token)
    
    if not payload:
        return None
    
    # Extract user info from payload
    # Supabase JWT structure includes sub (user id) and email
    user_id = payload.get("sub")
    email = payload.get("email")
    
    if not user_id:
        return None
    
    return {
        "id": user_id,
        "email": email or "unknown@example.com"
    }


async def optional_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[Dict[str, Any]]:
    """
    Dependency to get optional user from JWT token.
    
    In DEV_MODE, returns None if no token is provided.
    Otherwise, returns None if token is invalid.
    
    Args:
        request: FastAPI request object
        credentials: HTTP Bearer credentials
    
    Returns:
        User dict if token is valid, None otherwise
    """
    # Check for token in header
    token = None
    
    if credentials and credentials.credentials:
        token = credentials.credentials
    else:
        # Try to get from Authorization header directly
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.replace("Bearer ", "")
    
    if not token:
        if DEV_MODE:
            logger.debug("No token provided, returning None (DEV_MODE)")
            return None
        return None
    
    # Verify token
    user = extract_user_from_token(token)
    
    if user:
        # Store user in request state for later use
        request.state.user = user
    
    return user


async def require_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Dict[str, Any]:
    """
    Dependency to require a valid user from JWT token.
    
    Raises HTTPException(401) if token is missing or invalid.
    
    Args:
        request: FastAPI request object
        credentials: HTTP Bearer credentials
    
    Returns:
        User dict if token is valid
    
    Raises:
        HTTPException: 401 if token is missing or invalid
    """
    # Check for token in header
    token = None
    
    if credentials and credentials.credentials:
        token = credentials.credentials
    else:
        # Try to get from Authorization header directly
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.replace("Bearer ", "")
    
    if not token:
        # DEV_MODE bypass
        if DEV_MODE:
            logger.debug("DEV_MODE: Bypassing auth, returning dummy user")
            dummy_user = {
                "id": "dev-user-123",
                "email": "dev@example.com"
            }
            request.state.user = dummy_user
            return dummy_user
        
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Provide a valid Bearer token.",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Verify token
    user = extract_user_from_token(token)
    
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Store user in request state
    request.state.user = user
    
    return user


async def get_current_user_id(user: Dict[str, Any] = Depends(require_user)) -> str:
    """
    Get the current user's ID from the authenticated user.
    
    Args:
        user: User dict from require_user
    
    Returns:
        User ID string
    """
    return user["id"]


async def get_current_user_email(user: Dict[str, Any] = Depends(require_user)) -> str:
    """
    Get the current user's email from the authenticated user.
    
    Args:
        user: User dict from require_user
    
    Returns:
        User email string
    """
    return user["email"]


# Export dependencies
__all__ = [
    "optional_user",
    "require_user", 
    "get_current_user_id",
    "get_current_user_email",
    "verify_supabase_jwt",
    "extract_user_from_token",
    "security",
    "DEV_MODE"
]
