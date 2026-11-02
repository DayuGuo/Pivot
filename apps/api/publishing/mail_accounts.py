"""Mailbox metadata actions and read-only probes; no mail sending capability."""

import os
import re
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from packages.mail_adapters import MailCredentials, ProbeConfig, ProbeResult, probe

from .audit import record
from .db import get_db
from .models import MailAccount, now
from .policy import EDITOR_ROLES
from .security import Actor, get_actor

router = APIRouter(prefix="/api/mail", tags=["Mailbox bindings"])
ERRORS = {
    "invalid_configuration": "邮箱连接配置不合法，请检查服务器、端口和地址。",
    "provider_unsupported": "此邮件服务尚不支持。",
    "auth_mode_unsupported": "此服务不支持所选认证方式。",
    "credentials_missing": "尚未配置邮箱凭据，请联系管理员配置后重试。",
    "invalid_credentials": "凭据格式不合法，请更新服务器端凭据后重试。",
    "smtp_target_blocked": "该 SMTP 地址未在管理员允许列表中。",
    "smtp_tls_required": "自建邮箱必须使用 TLS；仅本地 Mailpit 可用明文测试连接。",
    "authentication_failed": "认证失败，请更新凭据或重新授权后重试。",
    "permission_denied": "邮件服务拒绝访问，请检查授权范围。",
    "rate_limited": "邮件服务请求过多，请稍后重试。",
    "provider_unavailable": "邮件服务暂不可用，请稍后重试。",
    "provider_response_invalid": "邮件服务返回了无法验证的响应。",
    "identity_mismatch": "授权邮箱与绑定地址不一致，请核对账号。",
    "redirect_blocked": "邮件服务发生了未授权重定向，连接已阻止。",
    "timeout": "连接超时，请检查邮件服务器后重试。",
    "network_error": "无法连接邮件服务器，请检查网络和地址。",
    "tls_failed": "TLS 验证失败，请检查服务器证书。",
    "smtp_protocol_error": "SMTP 服务器协议验证失败，请检查配置。",
    "probe_failed": "连接验证失败，请检查配置后重试。",
}


def local_mailpit_host() -> str:
    return os.getenv("MAILPIT_HOST", "mailpit").lower()


def allowed_smtp_targets() -> set[tuple[str, int]]:
    allowed = set()
    for entry in os.getenv("MAIL_SMTP_ALLOWLIST", "mailpit:1025").split(","):
        try:
            host, raw_port = entry.strip().rsplit(":", 1)
            port = int(raw_port)
            if re.fullmatch(r"[A-Za-z0-9.-]{1,253}", host) and 1 <= port <= 65535:
                allowed.add((host.lower(), port))
        except ValueError:
            continue
    return allowed


class MailAccountInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["smtp", "gmail", "outlook"]
    address: str = Field(min_length=3, max_length=254)
    display_name: str = Field(min_length=1, max_length=120)
    smtp_host: str | None = Field(default=None, max_length=253)
    smtp_port: int | None = Field(default=None, ge=1, le=65535, strict=True)
    tls_mode: Literal["starttls", "tls", "none"] | None = None
    auth_mode: Literal["none", "password", "oauth2"] | None = None
    username: str | None = Field(default=None, max_length=254)
    credential_ref: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,31}$")

    @model_validator(mode="after")
    def validate_binding(self):
        self.address = self.address.strip().lower()
        self.display_name = self.display_name.strip()
        if not re.fullmatch(
            r"[^\s@<>\x00-\x1f\x7f]+@[^\s@<>\x00-\x1f\x7f]+\.[^\s@<>\x00-\x1f\x7f]+", self.address
        ):
            raise ValueError("请填写合法邮箱地址")
        if not self.display_name or any(ord(c) < 32 for c in self.display_name):
            raise ValueError("请填写合法邮箱名称")
        if self.username is not None and (
            not self.username or any(ord(c) < 32 or ord(c) == 127 for c in self.username)
        ):
            raise ValueError("认证用户名不合法")
        if self.provider == "smtp":
            if not self.smtp_host:
                raise ValueError("自建邮件服务需要 SMTP 主机")
            self.smtp_host = self.smtp_host.strip().lower()
            if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", self.smtp_host):
                raise ValueError("SMTP 主机只能是域名或 IPv4 地址，不能包含 URL、用户信息或路径")
            self.smtp_port = self.smtp_port or 587
            self.tls_mode = self.tls_mode or "starttls"
            self.auth_mode = self.auth_mode or "none"
            if self.auth_mode == "oauth2":
                raise ValueError("自建 SMTP 当前仅支持无认证或密码认证")
            if self.tls_mode == "none" and (
                (self.smtp_host, self.smtp_port) != (local_mailpit_host(), 1025)
                or self.auth_mode != "none"
            ):
                raise ValueError("仅本地 Mailpit 无认证连接允许明文模式")
        else:
            if self.smtp_host is not None or self.smtp_port is not None:
                raise ValueError("Gmail/Outlook 使用固定官方 API，不接受自定义服务器")
            if self.auth_mode not in {None, "oauth2"}:
                raise ValueError("Gmail/Outlook 需要 OAuth2 访问令牌")
            self.auth_mode, self.tls_mode = "oauth2", "tls"
        return self


def mail_editor(actor: Actor = Depends(get_actor), db: Session = Depends(get_db)) -> Actor:
    if actor.role not in EDITOR_ROLES:
        record(
            db,
            actor_id=actor.user.id,
            journal_id=actor.journal_id,
            action="mail.action_denied",
            details={"role": actor.role},
        )
        db.commit()
        raise HTTPException(403, "只有编辑或主编可以管理期刊邮箱")
    return actor


def credentials_for(account: MailAccount) -> MailCredentials:
    ref = account.credential_ref
    if not ref or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,31}", ref):
        return MailCredentials()
    # A guessable ref must not let one journal borrow another journal's credentials.
    if os.getenv(f"MAIL_CREDENTIAL_{ref}_JOURNAL_ID") != account.journal_id:
        return MailCredentials()
    # Ref is an identifier in a dedicated namespace, never an arbitrary env-variable name.
    return MailCredentials(
        password=os.getenv(f"MAIL_CREDENTIAL_{ref}_PASSWORD") or None,
        access_token=os.getenv(f"MAIL_CREDENTIAL_{ref}_ACCESS_TOKEN") or None,
    )


def account_json(account: MailAccount) -> dict:
    credentials = credentials_for(account)
    configured = account.auth_mode != "none" and bool(
        credentials.password if account.auth_mode == "password" else credentials.access_token
    )
    return {
        "id": account.id,
        "provider": account.provider,
        "address": account.address,
        "display_name": account.display_name,
        "smtp_host": account.smtp_host,
        "smtp_port": account.smtp_port,
        "tls_mode": account.tls_mode,
        "auth_mode": account.auth_mode,
        "username": account.username,
        "credential_ref": account.credential_ref,
        "status": account.status,
        "last_error": account.last_error,
        "enabled": account.enabled,
        "last_checked_at": account.last_checked_at.isoformat() if account.last_checked_at else None,
        "created_at": account.created_at.isoformat(),
        "credentials_configured": configured,
    }


def owned_account(db: Session, actor: Actor, account_id: str) -> MailAccount:
    account = db.scalar(
        select(MailAccount)
        .where(MailAccount.id == account_id, MailAccount.journal_id == actor.journal_id)
        .with_for_update()
    )
    if not account:
        raise HTTPException(404, "邮箱绑定不存在或无权访问")
    return account


@router.get("/accounts")
def list_accounts(actor: Actor = Depends(mail_editor), db: Session = Depends(get_db)):
    accounts = db.scalars(
        select(MailAccount)
        .where(MailAccount.journal_id == actor.journal_id)
        .order_by(MailAccount.created_at.desc())
    ).all()
    return {"accounts": [account_json(a) for a in accounts], "email_send_enabled": False}


@router.post("/accounts")
def bind_account(
    body: MailAccountInput, actor: Actor = Depends(mail_editor), db: Session = Depends(get_db)
):
    account = db.scalar(
        select(MailAccount)
        .where(
            MailAccount.journal_id == actor.journal_id,
            MailAccount.provider == body.provider,
            MailAccount.address == body.address,
        )
        .with_for_update()
    )
    rebinding = account is not None
    if account:
        if account.enabled:
            raise HTTPException(409, "此期刊已保存相同服务和地址的邮箱")
        for field, value in body.model_dump().items():
            setattr(account, field, value)
        account.enabled, account.status = True, "unverified"
        account.last_checked_at, account.last_error = None, None
    else:
        account = MailAccount(
            **body.model_dump(),
            journal_id=actor.journal_id,
            created_by=actor.user.id,
            status="unverified",
            enabled=True,
        )
        db.add(account)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "此期刊已保存相同服务和地址的邮箱") from None
    record(
        db,
        actor_id=actor.user.id,
        journal_id=actor.journal_id,
        action="mail.account_rebound" if rebinding else "mail.account_bound",
        entity_id=account.id,
        details={"provider": account.provider, "address": account.address},
    )
    db.commit()
    return account_json(account)


@router.post("/accounts/{account_id}/verify")
def verify_account(
    account_id: UUID, actor: Actor = Depends(mail_editor), db: Session = Depends(get_db)
):
    account = owned_account(db, actor, str(account_id))
    if not account.enabled:
        raise HTTPException(409, "邮箱已断开，请重新绑定后再验证")
    try:
        result = probe(
            ProbeConfig(
                provider=account.provider,
                address=account.address,
                smtp_host=account.smtp_host,
                smtp_port=account.smtp_port,
                tls_mode=account.tls_mode,
                auth_mode=account.auth_mode,
                username=account.username,
            ),
            credentials_for(account),
            allowed_smtp_targets=allowed_smtp_targets(),
            local_mailpit_host=local_mailpit_host(),
        )
    except Exception:
        result = ProbeResult("error", "probe_failed")
    status, code = result.status, result.error_code
    if (
        status not in {"verified", "credentials_required", "blocked", "error"}
        or (code is not None and code not in ERRORS)
        or (status == "verified" and code is not None)
    ):
        status, code = "error", "probe_failed"
    if status != "verified" and code is None:
        code = "probe_failed"
    account.status = status
    account.last_checked_at = now()
    account.last_error = ERRORS[code] if code else None
    record(
        db,
        actor_id=actor.user.id,
        journal_id=actor.journal_id,
        action="mail.account_verified" if status == "verified" else "mail.verification_failed",
        entity_id=account.id,
        details={"provider": account.provider, "status": status, "error_code": code},
    )
    db.commit()
    return account_json(account)


@router.post("/accounts/{account_id}/disconnect")
def disconnect_account(
    account_id: UUID, actor: Actor = Depends(mail_editor), db: Session = Depends(get_db)
):
    account = owned_account(db, actor, str(account_id))
    if account.enabled:
        account.enabled, account.status = False, "disconnected"
        account.last_error = None
        record(
            db,
            actor_id=actor.user.id,
            journal_id=actor.journal_id,
            action="mail.account_disconnected",
            entity_id=account.id,
            details={"provider": account.provider},
        )
        db.commit()
    return account_json(account)
