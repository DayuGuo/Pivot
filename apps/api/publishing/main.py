import os
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from packages.model_gateway import MockModelProvider
from packages.model_gateway.editorial import editorial_model_status

from .audit import record
from .conversations import (
    conversation_json,
    create_conversation,
    latest_conversation,
    owned_conversation,
)
from .db import get_db
from .domain.api import router as publishing_router
from .domain.document_imports import router as document_import_router
from .domain.dossier_chat import router as dossier_chat_router
from .domain.dossiers import router as dossier_router
from .editorial_chat import router as editorial_chat_router
from .editorial_demo import router as editorial_demo_router
from .mail_accounts import router as mail_router
from .models import AuditEvent, Conversation, Journal, Manuscript, Message, User, now
from .policy import EDITOR_ROLES, can_view_manuscript
from .runtime import execute_command
from .security import Actor, check_password, get_actor, hash_password, new_session
from .serialization import manuscript_json, message_json, user_json
from .work_limits import HeavyWorkAdmission

# The original intake slice stays Mock. Workbench live configuration is independent.
provider = MockModelProvider()
app = FastAPI(title="Publishing OS", version="0.1.0")
app.add_middleware(HeavyWorkAdmission)
app.include_router(publishing_router)
app.include_router(dossier_router)
app.include_router(dossier_chat_router)
app.include_router(document_import_router)
app.include_router(mail_router)
app.include_router(editorial_demo_router)
app.include_router(editorial_chat_router)
DUMMY_HASH = hash_password("invalid-password-timing-padding")


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class CommandInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=2000)
    request_id: UUID
    conversation_id: UUID | None = None


class ConversationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(default="新对话", min_length=1, max_length=120)


@app.exception_handler(RequestValidationError)
async def safe_validation_error(request: Request, exc: RequestValidationError):
    # Pydantic defaults echo rejected inputs, including accidentally submitted passwords.
    return JSONResponse(
        status_code=422,
        content={
            "detail": "请求字段不合法，请检查输入。",
            "errors": [{"loc": list(error["loc"]), "msg": error["msg"]} for error in exc.errors()],
        },
    )


@app.middleware("http")
async def browser_boundary(request: Request, call_next):
    # Block cross-site browser mutations, including login CSRF, before credentials are read.
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if request.headers.get("sec-fetch-site") == "cross-site":
            from fastapi.responses import JSONResponse

            return JSONResponse({"detail": "跨站请求被禁止"}, status_code=403)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1 FROM alembic_version"))
    return {
        "status": "ok",
        "database": "postgresql",
        "email_send_enabled": False,
        "model_provider": "mock",
        "editorial_model": editorial_model_status(),
    }


@app.post("/api/auth/login")
def login(body: LoginInput, response: Response, db: Session = Depends(get_db)):
    # Persistent local-demo throttle. No passwords, raw cookies or API keys are audited.
    cutoff = now().timestamp() - 300
    failures = db.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(
            AuditEvent.action == "auth.login_failed",
            AuditEvent.details["email"].as_string() == body.email.lower(),
            func.extract("epoch", AuditEvent.created_at) >= cutoff,
        )
    )
    if failures >= 10:
        raise HTTPException(429, "登录尝试过多，请稍后重试")
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    valid = check_password(body.password, user.password_hash if user else DUMMY_HASH)
    if not user or not valid:
        record(
            db,
            actor_id=None,
            journal_id=None,
            action="auth.login_failed",
            details={"email": body.email.lower()},
        )
        db.commit()
        raise HTTPException(401, "邮箱或密码不正确")
    token, session = new_session(user)
    db.add(session)
    db.flush()
    # Resolve role with the same policy used for restored sessions.
    from .models import Membership

    memberships = db.scalars(select(Membership).where(Membership.user_id == user.id).limit(2)).all()
    if len(memberships) > 1:
        raise HTTPException(409, "账号关联多个工作期刊，请先配置明确的工作期刊")
    membership = memberships[0] if memberships else None
    if not membership:
        raise HTTPException(403, "没有期刊访问权限")
    actor = Actor(user, membership, session)
    record(
        db, actor_id=user.id, journal_id=actor.journal_id, action="auth.login", entity_id=user.id
    )
    db.commit()
    response.set_cookie(
        "publishing_session",
        token,
        httponly=True,
        samesite="strict",
        secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        max_age=28800,
        path="/",
    )
    return {"user": user_json(actor), "csrf_token": session.csrf_token}


@app.get("/api/auth/me")
def me(actor: Actor = Depends(get_actor)):
    return {"user": user_json(actor), "csrf_token": actor.session.csrf_token}


@app.post("/api/auth/logout")
def logout(response: Response, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    db.delete(actor.session)
    record(
        db,
        actor_id=actor.user.id,
        journal_id=actor.journal_id,
        action="auth.logout",
        entity_id=actor.user.id,
    )
    db.commit()
    response.delete_cookie("publishing_session", path="/")
    return {"ok": True}


@app.get("/api/workspace")
def workspace(
    conversation_id: UUID | None = None,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    journal = db.get(Journal, actor.journal_id)
    query = select(Manuscript).where(
        Manuscript.journal_id == actor.journal_id, Manuscript.workflow_kind == "legacy"
    )
    if actor.role == "author":
        query = query.where(Manuscript.author_id == actor.user.id)
    elif actor.role not in EDITOR_ROLES:
        query = query.where(False)
    manuscripts = db.scalars(query.order_by(Manuscript.created_at.desc())).all()
    active = (
        owned_conversation(db, actor, str(conversation_id))
        if conversation_id
        else latest_conversation(db, actor)
    )
    conversations = db.scalars(
        select(Conversation)
        .where(Conversation.user_id == actor.user.id, Conversation.journal_id == actor.journal_id)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
    ).all()
    messages = (
        db.scalars(
            select(Message)
            .where(Message.user_id == actor.user.id, Message.conversation_id == active.id)
            .order_by(Message.created_at, Message.id)
        ).all()
        if active
        else []
    )
    events = []
    if actor.role in EDITOR_ROLES:
        events = db.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.journal_id == actor.journal_id,
                ~AuditEvent.action.startswith("publishing."),
            )
            .order_by(AuditEvent.created_at.desc())
            .limit(100)
        ).all()
    return {
        "journal": {"id": journal.id, "name": journal.name},
        "manuscripts": [manuscript_json(db, m) for m in manuscripts],
        "messages": [message_json(m) for m in messages],
        "conversations": [conversation_json(db, c) for c in conversations],
        "active_conversation_id": active.id if active else None,
        "audit": [
            {
                "id": e.id,
                "action": e.action,
                "entity_id": e.entity_id,
                "actor_name": db.get(User, e.actor_id).name if e.actor_id else "系统",
                "details": e.details,
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ],
        "email_send_enabled": False,
    }


@app.get("/api/manuscripts/{manuscript_id}")
def manuscript_detail(
    manuscript_id: UUID, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)
):
    manuscript = db.get(Manuscript, str(manuscript_id))
    if not manuscript or not can_view_manuscript(actor, manuscript):
        raise HTTPException(404, "稿件不存在或无权访问")
    return manuscript_json(db, manuscript)


@app.post("/api/conversations/commands")
def command(body: CommandInput, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)):
    try:
        return execute_command(
            db,
            actor,
            body.message,
            str(body.request_id),
            provider,
            str(body.conversation_id) if body.conversation_id else None,
        )
    except HTTPException as exc:
        db.rollback()
        record(
            db,
            actor_id=actor.user.id,
            journal_id=actor.journal_id,
            action="action.denied",
            details={"status": exc.status_code, "request_id": str(body.request_id)},
        )
        db.commit()
        raise


@app.post("/api/conversations")
def new_conversation(
    body: ConversationInput, actor: Actor = Depends(get_actor), db: Session = Depends(get_db)
):
    title = body.title.strip()
    if not title or any(ord(c) < 32 for c in title):
        raise HTTPException(422, "请填写合法对话标题")
    item = create_conversation(db, actor, title)
    db.commit()
    return conversation_json(db, item)
