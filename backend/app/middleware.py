"""
Clerk JWT middleware.
Verifies Bearer tokens using Clerk's JWKS endpoint.
"""
import logging
import httpx
from functools import lru_cache
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt, jwk, JWTError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.company import Company, CompanyUser
from app.config import settings

logger = logging.getLogger("hireflow.middleware")
security = HTTPBearer(auto_error=False)

CLERK_JWKS_URL = "https://api.clerk.com/v1/jwks"


@lru_cache(maxsize=1)
def _fetch_jwks() -> dict:
    """Fetch Clerk JWKS (cached for performance)."""
    resp = httpx.get(CLERK_JWKS_URL, headers={"Authorization": f"Bearer {settings.CLERK_SECRET_KEY}"})
    resp.raise_for_status()
    return resp.json()


def verify_clerk_token(token: str) -> dict:
    """Verify a Clerk JWT and return decoded claims."""
    try:
        jwks = _fetch_jwks()
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")

        key_data = None
        for k in jwks.get("keys", []):
            if k.get("kid") == kid:
                key_data = k
                break

        if not key_data:
            raise HTTPException(status_code=401, detail="Public key not found")

        public_key = jwk.construct(key_data)
        claims = jwt.decode(token, public_key, algorithms=["RS256"])
        return claims
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> CompanyUser:
    """FastAPI dependency — returns the authenticated CompanyUser."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    claims = verify_clerk_token(credentials.credentials)
    clerk_user_id = claims.get("sub")
    clerk_org_id = claims.get("org_id")

    company = db.query(Company).filter(Company.clerk_org_id == clerk_org_id).first()
    if not company:
        raise HTTPException(status_code=403, detail="Company not found. Complete Clerk org setup.")

    user = db.query(CompanyUser).filter(
        CompanyUser.company_id == company.id,
        CompanyUser.clerk_user_id == clerk_user_id,
        CompanyUser.is_active == True,
    ).first()
    if not user:
        raise HTTPException(status_code=403, detail="User not found in company.")

    return user


def get_current_company(
    current_user: CompanyUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Company:
    """FastAPI dependency — returns the current user's Company."""
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


# Convenience alias used by all routers
require_auth = get_current_user
