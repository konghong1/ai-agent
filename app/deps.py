from __future__ import annotations

from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models import User


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    subject = decode_access_token(token)
    if not subject:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token.")
    user = db.get(User, int(subject))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")
    return user


def get_current_user_sse(
    request: Request,
    token_query: str | None = Query(None, alias="token"),
    db: Session = Depends(get_db),
) -> User:
    """Get current user from Authorization header OR ?token= query param.

    Specifically for SSE (EventSource) endpoints — browsers don't allow
    custom headers on EventSource connections, so we fall back to query
    parameter authentication.  Header is still tried first.
    """
    # Try Authorization header first, then the ?token= query param. EventSource
    # cannot set custom request headers, so SSE clients pass the JWT as a query
    # argument. Read it from both the FastAPI Query binding and the raw query
    # string as a belt-and-suspenders fallback (covers any Starlette/pydantic
    # version quirk in Query extraction for this dependency signature).
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        effective_token = auth_header.removeprefix("Bearer ")
    else:
        effective_token = token_query or request.query_params.get("token")

    if not effective_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Use Authorization header or ?token= query param.",
        )
    subject = decode_access_token(effective_token)
    if not subject:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token.")
    user = db.get(User, int(subject))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")
    return user
