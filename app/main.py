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
from pathlib import Path
from starlette.responses import Response
from typing import Generator, Dict

from .db import engine, Base, SessionLocal
from .models import User, Household, Task, Completion, PointsLedger
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
BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Household Tasks")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


limiter = Limiter(key_func=get_remote_address)

# Dependency


def get_db() -> Generator[Session, None, None]:
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
async def login_page(request: Request) -> Response:
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login")
@limiter.limit("20/minute")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
) -> Response:
    user = db.scalar(select(User).where(User.email == email))
    if not user or not verify_password(password, user.hash_pw):
        return templates.TemplateResponse(
            "login.html", {"request": request, "error": "Credenziali non valide"}
        )

    token = encode_session(
        {
            "user_id": user.id,
            "household_id": user.household_id,
            "email": user.email,
            "role": user.role,
        }
    )

    resp = RedirectResponse(url="/", status_code=303)  # <-- 303 per i POST redirect
    resp.set_cookie(
        key="session",
        value=token,
        httponly=True,
        secure=SESSION_SECURE,  # False in locale
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
        path="/",  # <-- importante per validità su tutte le route
    )
    return resp


@app.get("/logout")
async def logout() -> Response:
    resp = redirect("/login")
    resp.delete_cookie("session")
    return resp


# --- UI: dashboard ---
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)) -> Response:
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
@app.post("/tasks", response_class=HTMLResponse)
async def create_task(
    request: Request,
    title: str = Form(...),
    points: int = Form(1),
    priority: str = Form("medium"),
    due_date: str | None = Form(None),
    description: str | None = Form(None),
    db: Session = Depends(get_db),
) -> Response:
    from .security import decode_session

    data = decode_session(request.cookies.get("session", ""))
    if not data:
        raise HTTPException(status_code=401, detail="Not authenticated")

    due_date_obj = date.fromisoformat(due_date) if due_date else None

    task = Task(
        household_id=data["household_id"],
        title=title.strip(),
        description=(description or "").strip(),
        points=points,
        priority=priority,
        due_date=due_date_obj,
        created_by=data["user_id"],
        is_active=True,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    # per segnare correttamente lo stato "non completato"
    completed_ids: set[int] = set()

    # ritorniamo un <li> pronto da inserire nella UL con hx-swap="afterbegin"
    return templates.TemplateResponse(
        "_task_item.html",
        {
            "request": request,
            "t": task,
            "completed_ids": completed_ids,
        },
    )


@app.post("/tasks/{task_id}/complete")
async def complete_task(
    task_id: int, request: Request, db: Session = Depends(get_db)
) -> Dict[str, str]:
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
