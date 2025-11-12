from __future__ import annotations
from datetime import date
from fastapi import FastAPI, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import engine, Base, SessionLocal
from .models import User, Household, Task, Completion, PointsLedger
from .schemas import TaskCreate, TaskOut
from .security import hash_password, verify_password, encode_session, SESSION_SECURE

# --- DB init ---
Base.metadata.create_all(bind=engine)

# Bootstrap default admin/household
with SessionLocal() as db:
    if not db.scalar(select(Household).limit(1)):
        h = Household(name="Home")
        db.add(h)
        db.flush()
        admin = User(
            household_id=h.id,
            name="Admin",
            email="admin@example.com",
            hash_pw=hash_password("admin"),
            role="admin",
        )
        db.add(admin)
        db.commit()

# --- App init ---
app = FastAPI(title="Household Tasks")
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

limiter = Limiter(key_func=get_remote_address)

# Dependency


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- Helpers ---


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


# --- Auth routes (minimal, form-based) ---
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login")
@limiter.limit("20/minute")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.email == email))
    if not user or not verify_password(password, user.hash_pw):
        return templates.TemplateResponse(
            "login.html", {"request": request, "error": "Credenziali non valide"}
        )
    resp = redirect("/")
    token = encode_session(
        {
            "user_id": user.id,
            "household_id": user.household_id,
            "email": user.email,
            "role": user.role,
        }
    )
    resp.set_cookie(
        "session",
        token,
        httponly=True,
        secure=SESSION_SECURE,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
    )
    return resp


@app.get("/logout")
async def logout():
    resp = redirect("/login")
    resp.delete_cookie("session")
    return resp


# --- UI: dashboard ---
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("session")
    if not token:
        return redirect("/login")
    # naive decode (no error handling here; redirected by login otherwise)
    from .security import decode_session

    data = decode_session(token)
    if not data:
        return redirect("/login")

    today = date.today()
    tasks = db.scalars(
        select(Task)
        .where(
            Task.household_id == data["household_id"],
            Task.is_active,
        )
        .order_by(Task.due_date.is_(None), Task.due_date)
    ).all()

    completions = db.scalars(select(Completion)).all()
    completed_ids = {c.task_id for c in completions}

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": data,
            "tasks": tasks,
            "completed_ids": completed_ids,
            "today": today,
        },
    )


# --- API: tasks CRUD (minimal) ---
@app.post("/tasks", response_model=TaskOut)
async def create_task(
    payload: TaskCreate, request: Request, db: Session = Depends(get_db)
):
    from .security import decode_session

    data = decode_session(request.cookies.get("session", ""))
    if not data:
        raise HTTPException(status_code=401, detail="Not authenticated")

    task = Task(
        household_id=data["household_id"],
        title=payload.title.strip(),
        description=(payload.description or "").strip(),
        points=payload.points,
        priority=payload.priority,
        due_date=payload.due_date,
        created_by=data["user_id"],
        is_active=True,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@app.post("/tasks/{task_id}/complete")
async def complete_task(task_id: int, request: Request, db: Session = Depends(get_db)):
    from .security import decode_session

    data = decode_session(request.cookies.get("session", ""))
    if not data:
        raise HTTPException(status_code=401, detail="Not authenticated")
    task = db.get(Task, task_id)
    if not task or task.household_id != data["household_id"]:
        raise HTTPException(status_code=404, detail="Task non trovato")
    # idempotency light: if already completed, no double points
    already = db.scalar(
        select(Completion).where(
            Completion.task_id == task.id, Completion.user_id == data["user_id"]
        )
    )
    if already:
        return {"status": "already_done"}
    c = Completion(task_id=task.id, user_id=data["user_id"])
    db.add(c)
    db.add(
        PointsLedger(
            user_id=data["user_id"], delta=task.points, reason=f"Complete: {task.title}"
        )
    )
    db.commit()
    return {"status": "ok"}
