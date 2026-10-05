"""Authentication endpoints: registration, login (with 2FA), password reset and 2FA management."""

import hmac
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from hoje import audit, clock
from hoje.api._common import problems
from hoje.api.deps import (
    ActiveAuth,
    AppSettings,
    DbSession,
    OptionalAuth,
    SessionFactory,
    client_ip,
    get_mailer,
    get_session_factory,
    throttle_ip,
    user_agent,
)
from hoje.config import Settings
from hoje.models import PasswordResetToken, User
from hoje.schemas import (
    AuthState,
    LoginRequest,
    LoginResponse,
    Me,
    MfaRequest,
    PasswordChange,
    PasswordForgot,
    PasswordReset,
    RecoveryCodes,
    Register,
    TotpConfirmRequest,
    TotpEnableRequest,
    TotpSetupRequest,
    TotpSetupResponse,
)
from hoje.security import device, passwords
from hoje.security.device import DeviceCookie
from hoje.security.tokens import csrf_token, email_key
from hoje.services import password_reset, security_notice, sessions, throttle, twofactor, users
from hoje.services.mailer import Mailer
from hoje.services.sessions import AuthContext

router = APIRouter(prefix="/auth", tags=["auth"])

INVALID_LOGIN = "Invalid email or password"
INVALID_CODE = "Invalid code"
INVALID_RESET = "This reset link is invalid or has expired"
REAUTH_FAILED = "Incorrect password or code"
SETUP_TOKEN_REQUIRED = "A valid setup token is required"  # noqa: S105

MailerDep = Annotated[Mailer, Depends(get_mailer)]


async def _require_strong(password: str, email: str) -> None:
    weakness = await passwords.password_weakness_async(password, [email])
    if weakness is not None:
        raise HTTPException(status_code=422, detail=weakness)


def _reauth_key(user: User) -> str:
    return f"reauth:acct:{user.id}"


def _trusted_device(request: Request, settings: Settings, user: User | None) -> DeviceCookie | None:
    """The valid device cookie of this browser, if it was issued to ``user``."""
    if user is None:
        return None
    cookie = device.parse(
        settings.secret_key_bytes, request.cookies.get(device.cookie_name(settings)), clock.now()
    )
    return cookie if cookie is not None and cookie.user_id == user.id else None


def _queue_notice(
    background: BackgroundTasks,
    mailer: Mailer,
    settings: Settings,
    request: Request,
    user: User,
    event: security_notice.SecurityEvent,
) -> None:
    """Email the owner about a credential change after the response has been sent."""
    background.add_task(
        security_notice.send,
        mailer,
        event=event,
        to=user.email,
        user_id=user.id,
        timezone=user.timezone,
        ip=client_ip(request),
        when=clock.now(),
        public_url=settings.public_url,
    )


async def _reauthenticate(
    db: AsyncSession,
    settings: Settings,
    request: Request,
    user: User,
    *,
    password: str,
    code: str | None = None,
    allow_recovery: bool = False,
) -> None:
    """Re-check the password (and optionally a second factor) or raise 400 / 429."""
    key = _reauth_key(user)
    with audit.log_lockout("reauth", client_ip(request)):
        await throttle.ensure_not_locked(db, [key])
    ok = await passwords.verify_password(user.password_hash, password)
    if ok and code is not None:
        ok = await twofactor.verify_second_factor(
            db, settings, user, code, allow_recovery=allow_recovery
        )
    if not ok:
        await throttle.record_failure(db, key)
        await db.commit()
        audit.auth_failed("reauth", client_ip(request), user.email)
        raise HTTPException(status_code=400, detail=REAUTH_FAILED)
    await throttle.reset(db, key)


async def _finish_security_change(
    db: AsyncSession,
    request: Request,
    response: Response,
    settings: Settings,
    ctx: AuthContext,
) -> None:
    """After a credential change: revoke every session of the user and issue a fresh one."""
    await sessions.delete_user_sessions(db, ctx.user.id)
    raw, _ = await sessions.create(
        db,
        ctx.user.id,
        stage=sessions.STAGE_ACTIVE,
        ip=client_ip(request),
        user_agent=user_agent(request),
    )
    await db.commit()
    sessions.set_cookie(response, settings, raw, sessions.STAGE_ACTIVE)


async def _check_setup_token(
    db: AsyncSession, request: Request, settings: Settings, supplied: str | None
) -> None:
    """Gate the first registration on HOJE_SETUP_TOKEN; failures feed the IP lockout."""
    if not await users.setup_token_required(db, settings) or settings.setup_token is None:
        return
    key = f"register:ip:{throttle_ip(request)}"
    with audit.log_lockout("setup_token", client_ip(request)):
        await throttle.ensure_not_locked(db, [key])
    expected = settings.setup_token.get_secret_value().encode()
    if supplied is None or not hmac.compare_digest(supplied.encode(), expected):
        await throttle.record_failure(db, key)
        await db.commit()
        audit.auth_failed("setup_token", client_ip(request))
        raise HTTPException(status_code=403, detail=SETUP_TOKEN_REQUIRED)


@router.get("/state", response_model=AuthState, summary="Current authentication state")
async def auth_state(db: DbSession, settings: AppSettings, ctx: OptionalAuth) -> AuthState:
    registration_open = await users.registration_open(db, settings)
    token_required = await users.setup_token_required(db, settings)
    if ctx is None:
        return AuthState(
            registration_open=registration_open,
            setup_token_required=token_required,
            authenticated=False,
        )
    token = csrf_token(settings.secret_key_bytes, ctx.session.csrf_secret)
    if ctx.session.stage == sessions.STAGE_ACTIVE:
        return AuthState(
            registration_open=registration_open,
            setup_token_required=token_required,
            authenticated=True,
            stage="active",
            csrf_token=token,
            user=Me.model_validate(ctx.user),
        )
    return AuthState(
        registration_open=registration_open,
        setup_token_required=token_required,
        authenticated=False,
        stage="mfa_pending",
        csrf_token=token,
    )


@router.post(
    "/register",
    response_model=Me,
    status_code=201,
    responses=problems(403, 409, 429),
    summary="Register the first user",
)
async def auth_register(
    body: Register,
    request: Request,
    response: Response,
    db: DbSession,
    settings: AppSettings,
    ctx: OptionalAuth,
) -> Me:
    if not await users.registration_open(db, settings):
        raise HTTPException(status_code=403, detail="Registration is closed")
    await _check_setup_token(db, request, settings, body.setup_token)
    await _require_strong(body.password, body.email)
    try:
        user = await users.register(db, settings, email=body.email, password=body.password)
    except users.RegistrationClosedError:
        raise HTTPException(status_code=403, detail="Registration is closed") from None
    except users.EmailTakenError:
        raise HTTPException(
            status_code=409, detail="An account with this email already exists"
        ) from None
    if ctx is not None:
        await sessions.delete_session(db, ctx.session.id)
    raw, _ = await sessions.create(
        db,
        user.id,
        stage=sessions.STAGE_ACTIVE,
        ip=client_ip(request),
        user_agent=user_agent(request),
    )
    me = Me.model_validate(user)
    await db.commit()
    sessions.set_cookie(response, settings, raw, sessions.STAGE_ACTIVE)
    audit.auth_event("registered", user.id, client_ip(request))
    return me


@router.post(
    "/login",
    response_model=LoginResponse,
    responses=problems(401, 429),
    summary="Log in with email and password",
)
async def auth_login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: DbSession,
    settings: AppSettings,
    ctx: OptionalAuth,
) -> LoginResponse:
    ip = client_ip(request)
    user = await users.get_by_email(db, body.email)
    # A browser that already signed in to this account is throttled on its own device key, not
    # on the per-account key that any stranger knowing the email address can fill (S-02).
    trusted = _trusted_device(request, settings, user)
    ip_key = f"login:ip:{throttle_ip(request)}"
    subject_key = (
        trusted.throttle_key if trusted is not None else f"login:acct:{email_key(body.email)}"
    )
    with audit.log_lockout("login", ip):
        await throttle.ensure_not_locked(db, [ip_key, subject_key])

    # Unknown accounts are verified against a dummy hash so timing does not reveal existence.
    ok = await passwords.verify_password(user.password_hash if user else None, body.password)
    if user is None or not ok:
        await throttle.record_failure(db, ip_key, subject_key)
        await db.commit()
        audit.auth_failed("login", ip, body.email)
        raise HTTPException(status_code=401, detail=INVALID_LOGIN)

    if passwords.needs_rehash(user.password_hash):
        await users.set_password(db, user, body.password)
    await throttle.reset(db, subject_key)
    await throttle.purge_stale(db)
    await sessions.purge_expired(db, user.id)

    stage = sessions.STAGE_MFA_PENDING if user.totp_enabled else sessions.STAGE_ACTIVE
    raw, _ = await sessions.rotate(
        db,
        ctx.session if ctx is not None else None,
        user.id,
        stage=stage,
        ip=ip,
        user_agent=user_agent(request),
    )
    await db.commit()
    sessions.set_cookie(response, settings, raw, stage)
    if not user.totp_enabled:  # with 2FA the device cookie waits for the second factor
        device.set_cookie(response, settings, user.id, clock.now())
        audit.auth_event("login_ok", user.id, ip)
    return LoginResponse(status="mfa_required" if user.totp_enabled else "ok")


@router.post(
    "/login/mfa",
    response_model=LoginResponse,
    responses=problems(401, 429),
    summary="Complete login with a 2FA code",
)
async def auth_login_mfa(
    body: MfaRequest,
    request: Request,
    response: Response,
    db: DbSession,
    settings: AppSettings,
    ctx: OptionalAuth,
) -> LoginResponse:
    if ctx is None or ctx.session.stage != sessions.STAGE_MFA_PENDING:
        raise HTTPException(status_code=401, detail="Not authenticated")
    ip = client_ip(request)
    keys = [f"mfa:sess:{ctx.session.id}", f"mfa:acct:{ctx.user.id}"]
    with audit.log_lockout("mfa", ip):
        await throttle.ensure_not_locked(db, keys)
    ok = await twofactor.verify_second_factor(
        db, settings, ctx.user, body.code, allow_recovery=True
    )
    if not ok:
        await throttle.record_failure(db, *keys)
        await db.commit()
        audit.auth_failed("mfa", ip, ctx.user.email)
        raise HTTPException(status_code=401, detail=INVALID_CODE)
    await throttle.reset(db, *keys)
    raw, _ = await sessions.rotate(
        db,
        ctx.session,
        ctx.user.id,
        stage=sessions.STAGE_ACTIVE,
        ip=ip,
        user_agent=user_agent(request),
    )
    await db.commit()
    sessions.set_cookie(response, settings, raw, sessions.STAGE_ACTIVE)
    device.set_cookie(response, settings, ctx.user.id, clock.now())
    audit.auth_event("login_ok", ctx.user.id, ip)
    return LoginResponse(status="ok")


@router.post("/logout", status_code=204, summary="Log out")
async def auth_logout(
    response: Response, db: DbSession, settings: AppSettings, ctx: OptionalAuth
) -> None:
    if ctx is not None:
        await sessions.delete_session(db, ctx.session.id)
        await db.commit()
    sessions.clear_cookie(response, settings)


@router.post(
    "/password/forgot",
    status_code=202,
    responses=problems(429),
    summary="Request a password reset email",
)
async def auth_password_forgot(
    body: PasswordForgot,
    request: Request,
    background: BackgroundTasks,
    db: DbSession,
    settings: AppSettings,
    mailer: MailerDep,
    factory: Annotated[SessionFactory, Depends(get_session_factory)],
) -> None:
    ip = client_ip(request)
    # A shared per-account budget would let a stranger use up the owner's reset requests; a
    # browser the owner already signed in with spends its own device budget instead.
    trusted = _trusted_device(request, settings, await users.get_by_email(db, body.email))
    subject_key = (
        f"forgot:dev:{trusted.nonce}"
        if trusted is not None
        else f"forgot:acct:{email_key(body.email)}"
    )
    with audit.log_lockout("forgot", ip):
        await throttle.hit(db, f"forgot:ip:{throttle_ip(request)}", subject_key)
    # Same work and same response whether or not the account exists: the lookup and the
    # email happen after the response has been sent.
    background.add_task(
        password_reset.issue_and_send,
        factory,
        mailer,
        settings,
        email=body.email,
        requested_ip=ip,
    )


@router.post(
    "/password/reset",
    status_code=204,
    responses=problems(400, 429),
    summary="Reset a password with a token",
)
async def auth_password_reset(
    body: PasswordReset,
    request: Request,
    background: BackgroundTasks,
    db: DbSession,
    settings: AppSettings,
    mailer: MailerDep,
) -> None:
    ip = client_ip(request)
    with audit.log_lockout("reset", ip):
        await throttle.hit(db, f"reset:ip:{throttle_ip(request)}")
    token = await password_reset.lock_valid_token(db, body.token)
    user = await users.get_by_id(db, token.user_id) if token is not None else None
    if user is None:
        audit.auth_failed("reset", ip)
        raise HTTPException(status_code=400, detail=INVALID_RESET)
    await _require_strong(body.new_password, user.email)
    await users.set_password(db, user, body.new_password)
    await db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
        .values(used_at=clock.now())
    )
    await sessions.delete_user_sessions(db, user.id)
    await throttle.reset(db, f"login:acct:{email_key(user.email)}", _reauth_key(user))
    await db.commit()
    audit.auth_event("password_reset", user.id, ip)
    _queue_notice(background, mailer, settings, request, user, "password_reset")


@router.post(
    "/password/change",
    status_code=204,
    responses=problems(400, 429),
    summary="Change the current password",
)
async def auth_password_change(
    body: PasswordChange,
    request: Request,
    response: Response,
    background: BackgroundTasks,
    db: DbSession,
    settings: AppSettings,
    mailer: MailerDep,
    ctx: ActiveAuth,
) -> None:
    user = ctx.user
    await _reauthenticate(db, settings, request, user, password=body.current_password)
    await _require_strong(body.new_password, user.email)
    await users.set_password(db, user, body.new_password)
    await _finish_security_change(db, request, response, settings, ctx)
    audit.auth_event("password_changed", user.id, client_ip(request))
    _queue_notice(background, mailer, settings, request, user, "password_changed")


@router.post(
    "/2fa/setup",
    response_model=TotpSetupResponse,
    responses=problems(400, 409, 429),
    summary="Begin TOTP enrolment",
)
async def auth_2fa_setup(
    body: TotpSetupRequest,
    request: Request,
    db: DbSession,
    settings: AppSettings,
    ctx: ActiveAuth,
) -> TotpSetupResponse:
    user = ctx.user
    await db.refresh(user, with_for_update=True)
    if user.totp_enabled:
        raise HTTPException(status_code=409, detail="Two-factor authentication is already enabled")
    await _reauthenticate(db, settings, request, user, password=body.password)
    secret, uri, svg = await twofactor.begin_setup(db, settings, user)
    await db.commit()
    return TotpSetupResponse(otpauth_uri=uri, secret=secret, qr_svg=svg)


@router.post(
    "/2fa/enable",
    response_model=RecoveryCodes,
    responses=problems(400, 409, 429),
    summary="Confirm TOTP enrolment",
)
async def auth_2fa_enable(
    body: TotpEnableRequest,
    request: Request,
    response: Response,
    db: DbSession,
    settings: AppSettings,
    ctx: ActiveAuth,
) -> RecoveryCodes:
    user = ctx.user
    await db.refresh(user, with_for_update=True)
    if user.totp_enabled:
        raise HTTPException(status_code=409, detail="Two-factor authentication is already enabled")
    if user.totp_pending_enc is None:
        raise HTTPException(status_code=409, detail="Start two-factor setup first")
    key = _reauth_key(user)
    with audit.log_lockout("reauth", client_ip(request)):
        await throttle.ensure_not_locked(db, [key])
    if not await twofactor.confirm_enable(db, settings, user, body.code):
        await throttle.record_failure(db, key)
        await db.commit()
        audit.auth_failed("reauth", client_ip(request), user.email)
        raise HTTPException(status_code=400, detail=INVALID_CODE)
    await throttle.reset(db, key)
    codes = await twofactor.replace_recovery_codes(db, user)
    await _finish_security_change(db, request, response, settings, ctx)
    audit.auth_event("2fa_enabled", user.id, client_ip(request))
    return RecoveryCodes(recovery_codes=codes)


@router.post(
    "/2fa/disable",
    status_code=204,
    responses=problems(400, 409, 429),
    summary="Disable 2FA",
)
async def auth_2fa_disable(
    body: TotpConfirmRequest,
    request: Request,
    response: Response,
    background: BackgroundTasks,
    db: DbSession,
    settings: AppSettings,
    mailer: MailerDep,
    ctx: ActiveAuth,
) -> None:
    user = ctx.user
    await db.refresh(user, with_for_update=True)
    if not user.totp_enabled:
        raise HTTPException(status_code=409, detail="Two-factor authentication is not enabled")
    await _reauthenticate(
        db, settings, request, user, password=body.password, code=body.code, allow_recovery=True
    )
    await twofactor.disable(db, user)
    await _finish_security_change(db, request, response, settings, ctx)
    audit.auth_event("2fa_disabled", user.id, client_ip(request))
    _queue_notice(background, mailer, settings, request, user, "2fa_disabled")


@router.post(
    "/2fa/recovery-codes",
    response_model=RecoveryCodes,
    responses=problems(400, 409, 429),
    summary="Regenerate recovery codes",
)
async def auth_2fa_recovery_codes(
    body: TotpConfirmRequest,
    request: Request,
    response: Response,
    background: BackgroundTasks,
    db: DbSession,
    settings: AppSettings,
    mailer: MailerDep,
    ctx: ActiveAuth,
) -> RecoveryCodes:
    user = ctx.user
    await db.refresh(user, with_for_update=True)
    if not user.totp_enabled:
        raise HTTPException(status_code=409, detail="Two-factor authentication is not enabled")
    await _reauthenticate(db, settings, request, user, password=body.password, code=body.code)
    codes = await twofactor.replace_recovery_codes(db, user)
    await _finish_security_change(db, request, response, settings, ctx)
    audit.auth_event("recovery_regenerated", user.id, client_ip(request))
    _queue_notice(background, mailer, settings, request, user, "recovery_regenerated")
    return RecoveryCodes(recovery_codes=codes)
