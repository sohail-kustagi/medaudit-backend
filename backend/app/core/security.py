import json
import urllib.request
from typing import Any, Dict, Optional
import jwt
from fastapi import HTTPException, status
from backend.app.config import settings

# In-memory cache for Cognito JWKS
_jwks_cache: Optional[Dict[str, Any]] = None


def get_cognito_jwks() -> Dict[str, Any]:
    global _jwks_cache
    if _jwks_cache is not None:
        return _jwks_cache

    if not settings.COGNITO_USER_POOL_ID or settings.COGNITO_USER_POOL_ID == "us-east-1_mock":
        return {"keys": []}

    jwks_url = f"https://cognito-idp.{settings.COGNITO_REGION}.amazonaws.com/{settings.COGNITO_USER_POOL_ID}/.well-known/jwks.json"
    try:
        req = urllib.request.Request(jwks_url, headers={"User-Agent": "MedAudit-Backend"})
        with urllib.request.urlopen(req, timeout=5) as response:
            _jwks_cache = json.loads(response.read().decode("utf-8"))
            return _jwks_cache
    except Exception as e:
        if settings.ALLOW_MOCK_AUTH:
            return {"keys": []}
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Unable to reach AWS Cognito JWKS service: {str(e)}",
        )


def verify_cognito_token(token: str) -> Dict[str, Any]:
    """
    Validates a JWT token against AWS Cognito or dev mock fallback.
    Returns token claims dict with 'sub' and 'email'.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization token missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Dev / Mock token support
    if settings.ALLOW_MOCK_AUTH and (token.startswith("mock-") or token.startswith("test-") or "mock" in token):
        sub_id = token.replace("Bearer ", "").strip()
        return {
            "sub": sub_id,
            "email": f"{sub_id}@example.com",
            "name": "Test User",
            "token_use": "access"
        }

    try:
        unverified_header = jwt.get_unverified_header(token)
    except Exception:
        if settings.ALLOW_MOCK_AUTH:
            return {
                "sub": "dev-user-mock-id",
                "email": "dev-user@example.com",
                "name": "Dev User",
                "token_use": "access"
            }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    jwks = get_cognito_jwks()
    rsa_key = {}
    for key in jwks.get("keys", []):
        if key.get("kid") == unverified_header.get("kid"):
            rsa_key = {
                "kty": key["kty"],
                "kid": key["kid"],
                "use": key.get("use"),
                "n": key["n"],
                "e": key["e"],
            }
            break

    if not rsa_key:
        if settings.ALLOW_MOCK_AUTH:
            # Decode payload unverified in development mode if mock enabled
            try:
                payload = jwt.decode(token, options={"verify_signature": False})
                if "sub" in payload:
                    return payload
            except Exception:
                pass
            return {
                "sub": "dev-user-mock-id",
                "email": "dev-user@example.com",
                "name": "Dev User",
            }

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unable to find matching RSA key in Cognito JWKS",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(rsa_key))
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=settings.COGNITO_CLIENT_ID,
            issuer=f"https://cognito-idp.{settings.COGNITO_REGION}.amazonaws.com/{settings.COGNITO_USER_POOL_ID}",
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token verification failed: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
