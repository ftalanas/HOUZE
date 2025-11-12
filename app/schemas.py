from __future__ import annotations
from datetime import date
from typing import Optional, Literal
from pydantic import BaseModel, Field, EmailStr


class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    points: int = Field(ge=0, default=1)
    priority: Literal["low", "medium", "high"] = "medium"
    due_date: Optional[date] = None


class TaskOut(BaseModel):
    id: int
    title: str
    points: int
    priority: str
    due_date: Optional[date]
    is_active: bool


class Config:
    from_attributes = True


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str


class LoginIn(BaseModel):
    email: EmailStr
    password: str
