import os
import logging
import jwt
from jwt import PyJWKClient

TENANT_ID = os.environ.get("ENTRA_TENANT_ID")
CLIENT_ID = os.environ.get("ENTRA_CLIENT_ID")

JWKS_URL = f"https://login.microsoftonline.com/{TENANT_ID}/discovery/v2.0/keys"
ISSUER = f"https://sts.windows.net/{TENANT_ID}/"
logging.warning(f"DEBUG: TENANT_ID={repr(TENANT_ID)} ISSUER={repr(ISSUER)}")

_jwk_client = None


def _get_jwk_client():
    global _jwk_client
    if _jwk_client is None:
        _jwk_client = PyJWKClient(JWKS_URL)
    return _jwk_client


class AuthError(Exception):
    """Raised when a token is missing, invalid, expired, or lacks a required role."""
    def __init__(self, message: str, status_code: int = 401):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def validate_token(auth_header: str) -> dict:
    """
    Validates the Authorization header's bearer token against Entra ID.
    Returns the decoded token claims on success.
    Raises AuthError on any failure (missing header, bad signature,
    expired, wrong audience/issuer).
    """
    if not auth_header or not auth_header.startswith("Bearer "):
        raise AuthError("Missing or malformed Authorization header", 401)

    token = auth_header.removeprefix("Bearer ").strip()

    try:
        signing_key = _get_jwk_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=f"api://{CLIENT_ID}",
            issuer=ISSUER,
        )
        return claims
    except jwt.ExpiredSignatureError:
        raise AuthError("Token has expired", 401)
    except jwt.InvalidTokenError as e:
        logging.error(f"Token validation failed: {e}")
        raise AuthError("Invalid token", 401)


def require_role(claims: dict, required_role: str) -> None:
    """
    Checks that the given decoded token claims include the required app role.
    Raises AuthError (403) if the role is missing.
    """
    roles = claims.get("roles", [])
    if required_role not in roles:
        raise AuthError(f"Requires '{required_role}' role", 403)