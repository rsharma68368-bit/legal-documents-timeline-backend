"""
Authentication: Supabase JWT validation and current user dependency.

We only validate the JWT; we do not use Supabase's database. User records are in MongoDB.

Supabase can sign JWTs with:
- RS256/ES256 (asymmetric): verify using public keys from JWKS (recommended).
- HS256 (legacy): verify using SUPABASE_JWT_SECRET.

We support both: read the token header; if alg is RS256/ES256 we use JWKS,
otherwise HS256 with the secret.
"""

import logging
from typing import Annotated, Any

import jwt
from jwt import PyJWKClient
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings
from app.models.user import User

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=True)


def _get_jwks_url() -> str:
    """JWKS URL for this Supabase project (public keys for RS256/ES256)."""
    base = (get_settings().supabase_url or "").rstrip("/")
    if not base or "your-project" in base:
        raise ValueError("Set SUPABASE_URL in .env to your project URL (e.g. https://xxx.supabase.co)")
    return f"{base}/auth/v1/.well-known/jwks.json"


def _decode_token_rs256_es256(token: str) -> dict[str, Any]:
    """Verify JWT using Supabase JWKS (RS256 or ES256)."""
    jwks_url = _get_jwks_url()
    client = PyJWKClient(jwks_url)
    signing_key = client.get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256", "ES256"],
        options={"verify_aud": False},
    )


def _decode_token_hs256(token: str, secret: str) -> dict[str, Any]:
    """Verify JWT using shared secret (legacy Supabase)."""
    return jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        options={"verify_aud": False},
    )


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
) -> User:
    """
    Dependency: validate Supabase JWT and return the corresponding User from MongoDB.
    Supports RS256/ES256 (via JWKS) and HS256 (via SUPABASE_JWT_SECRET).
    """
    token = credentials.credentials
    settings = get_settings()

    # Read header without verifying to choose verification method
    try:
        unverified = jwt.get_unverified_header(token)
    except Exception as e:
        logger.warning("Invalid JWT header: %s", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token format")

    alg = unverified.get("alg")
    if not alg:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing algorithm")

    payload: dict[str, Any] | None = None

    if alg in ("RS256", "ES256"):
        try:
            payload = _decode_token_rs256_es256(token)
        except ValueError as e:
            logger.warning("JWKS URL misconfigured: %s", e)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Set SUPABASE_URL in backend .env to your project URL (e.g. https://xxx.supabase.co).",
            )
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired")
        except jwt.InvalidTokenError as e:
            logger.warning("JWT verification failed (JWKS): %s", e)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token. Ensure SUPABASE_URL in .env is your project URL (e.g. https://xxx.supabase.co).",
            )
    elif alg == "HS256":
        secret = settings.supabase_jwt_secret
        if not secret:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication not configured (SUPABASE_JWT_SECRET required for HS256).",
            )
        try:
            payload = _decode_token_hs256(token, secret)
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired")
        except jwt.InvalidTokenError as e:
            logger.warning("JWT verification failed (HS256): %s", e)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token. Check SUPABASE_JWT_SECRET in .env.",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Unsupported token algorithm: {alg}",
        )

    # Standard JWT claims: sub = subject (user id in Supabase)
    supabase_id: str = payload.get("sub")
    if not supabase_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject",
        )
    email: str | None = payload.get("email")

    # Create or sync user in our DB (async to avoid blocking the event loop)
    user = await User.find_one(User.supabase_id == supabase_id)
    if not user:
        user = User(supabase_id=supabase_id, email=email)
        await user.insert()
        logger.info("Created new user for supabase_id=%s", supabase_id)
    elif email and user.email != email:
        user.email = email
        await user.save_changes()
        logger.info("Updated email for user %s", user.id)

    return user
