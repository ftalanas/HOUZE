from __future__ import annotations
from fastapi import Request, HTTPException
from .security import decode_session


async def get_current_user(request: Request):
    token = request.cookies.get("session")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    data = decode_session(token)
    if not data:
        raise HTTPException(status_code=401, detail="Invalid session")
    return data  # {"user_id": int, "household_id": int, "email": str, "role": str}
