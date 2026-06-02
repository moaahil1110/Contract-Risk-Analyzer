"""
Authentication Middleware
Priority 4: Hardened auth with production fail-closed and owner enforcement.
"""

import os
import jwt
import logging
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

# Security scheme for Swagger UI
security = HTTPBearer(auto_error=False)

# DEV_MODE: if true, auth is optional with deterministic dummy user
DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"

# JWT configuration
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
SUPABASE_JWKS_URL = os.getenv("SUPABASE_JWKS_URL")
SUPPORTED_ASYMMETRIC_ALGORITHMS = ["ES256", "RS256"]

_jwks_client: Optional[jwt.PyJWKClient] = None

# Dummy dev user used when DEV_MODE=true and no token is provided
_DEV_USER = {
    "id": "dev-user-123",
    "email": "dev@example.com",
}


def validate_security_config_at_startup():
    """
    Fail closed in production if required security env vars are missing.
    Called during application startup.
    """
    if DEV_MODE:
        logger.warning("DEV_MODE=true: Authentication is optional. Do NOT use in production.")
        return

    missing = []
    if not SUPABASE_URL:
        missing.append("SUPABASE_URL")
    if not SUPABASE_SERVICE_KEY:
        missing.append("SUPABASE_SERVICE_KEY")

    if missing:
        raise RuntimeError(
            f"Production security configuration incomplete. Missing: {', '.join(missing)}. "
            f"Set these environment variables or enable DEV_MODE for local development only."
        )


def _get_jwks_url() -> Optional[str]:
    if SUPABASE_JWKS_URL:
        return SUPABASE_JWKS_URL
    if SUPABASE_URL:
        return f"{SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"
    return None


def _get_jwks_client() -> jwt.PyJWKClient:
    global _jwks_client
    jwks_url = _get_jwks_url()
    if not jwks_url:
        raise RuntimeError("SUPABASE_URL or SUPABASE_JWKS_URL is required for asymmetric JWT verification")
    if _jwks_client is None:
        _jwks_client = jwt.PyJWKClient(jwks_url)
    return _jwks_client


def verify_supabase_jwt(token: str) -> Optional[Dict[str, Any]]:
    """
    Verify a Supabase JWT token and return the decoded payload.
    In production, signature verification is mandatory.
    In DEV_MODE, unsigned tokens may be decoded with a warning.
    """
    try:
        header = jwt.get_unverified_header(token)
        algorithm = header.get("alg")

        if algorithm == "HS256":
            if not SUPABASE_JWT_SECRET:
                if not DEV_MODE:
                    logger.error("SUPABASE_JWT_SECRET is required for HS256 token verification")
                    return None
                payload = jwt.decode(
                    token,
                    options={"verify_signature": False},
                    algorithms=["HS256"],
                )
                logger.warning("DEV_MODE: Verifying HS256 JWT without signature")
                return payload

            payload = jwt.decode(
                token,
                SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience="authenticated",
            )
            return payload

        if algorithm in SUPPORTED_ASYMMETRIC_ALGORITHMS:
            signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
            return jwt.decode(
                token,
                signing_key.key,
                algorithms=SUPPORTED_ASYMMETRIC_ALGORITHMS,
                audience="authenticated",
            )

        logger.warning(f"Unsupported JWT algorithm: {algorithm}")
        return None

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
    Enforces role=authenticated, valid sub, valid exp, and expected audience.
    """
    payload = verify_supabase_jwt(token)
    if not payload:
        return None

    user_id = payload.get("sub")
    email = payload.get("email")
    role = payload.get("role")
    exp = payload.get("exp")

    if not user_id:
        logger.warning("JWT missing 'sub' claim")
        return None

    if not exp:
        logger.warning("JWT missing 'exp' claim")
        return None

    if role != "authenticated":
        logger.warning(f"JWT unexpected role: {role}")
        return None

    return {
        "id": user_id,
        "email": email or "unknown@example.com",
        "role": role,
    }


async def optional_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[Dict[str, Any]]:
    """
    Dependency to get optional user from JWT token.
    In DEV_MODE, returns None if no token is provided.
    Otherwise, returns None if token is invalid.
    """
    token = None

    if credentials and credentials.credentials:
        token = credentials.credentials
    else:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.replace("Bearer ", "")

    if not token:
        if DEV_MODE:
            logger.debug("No token provided, returning None (DEV_MODE)")
            return None
        return None

    user = extract_user_from_token(token)

    if user:
        request.state.user = user

    return user


async def require_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Dict[str, Any]:
    """
    Dependency to require a valid user from JWT token.
    In DEV_MODE, returns a deterministic dummy user if no token is provided.
    Raises HTTPException(401) if token is missing or invalid in production.
    """
    token = None

    if credentials and credentials.credentials:
        token = credentials.credentials
    else:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.replace("Bearer ", "")

    if not token:
        if DEV_MODE:
            logger.debug("DEV_MODE: Bypassing auth, returning dummy user")
            request.state.user = _DEV_USER
            return _DEV_USER

        raise HTTPException(
            status_code=401,
            detail="Authentication required. Provide a valid Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = extract_user_from_token(token)

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    request.state.user = user
    return user


async def get_current_user_id(user: Dict[str, Any] = Depends(require_user)) -> str:
    """Get the current user's ID from the authenticated user."""
    return user["id"]


async def get_current_user_email(user: Dict[str, Any] = Depends(require_user)) -> str:
    """Get the current user's email from the authenticated user."""
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
    "DEV_MODE",
    "validate_security_config_at_startup",
]
