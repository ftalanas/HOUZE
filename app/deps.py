from __future__ import annotations
from fastapi import Request, HTTPException
from .security import decode_session
from typing import Generator
from .db import SessionLocal
from sqlalchemy.orm import Session
from typing import TypedDict, cast


class SessionData(TypedDict):
    user_id: int
    household_id: int
    email: str
    role: str


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_current_user(request: Request) -> SessionData:
    token = request.cookies.get("session")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    data = decode_session(token)
    if not data:
        raise HTTPException(status_code=401, detail="Invalid session")
    return cast(
        SessionData, data
    )  # {"user_id": int, "household_id": int, "email": str, "role": str}
