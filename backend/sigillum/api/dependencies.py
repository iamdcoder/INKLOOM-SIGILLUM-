from typing import Annotated
import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session
from sigillum.infrastructure.database.session import get_db
from sigillum.infrastructure.database.models import User
from sigillum.infrastructure.security import decode_access_token
from sigillum.domain.enums import Role

DbSession = Annotated[Session, Depends(get_db)]

def current_user(authorization: Annotated[str | None, Header()] = None, db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code":"AUTH_REQUIRED", "message":"Sign in to continue."})
    try:
        payload = decode_access_token(authorization.split(" ", 1)[1])
        user = db.get(User, payload.get("sub"))
    except (jwt.InvalidTokenError, ValueError, TypeError):
        user = None
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail={"code":"INVALID_SESSION", "message":"Session is invalid or expired."})
    return user

CurrentUser = Annotated[User, Depends(current_user)]

def require_roles(*roles: Role):
    def dependency(user: CurrentUser) -> User:
        if Role(user.role) not in roles:
            raise HTTPException(status_code=403, detail={"code":"ACCESS_DENIED", "message":"Your role cannot perform this action."})
        return user
    return dependency
