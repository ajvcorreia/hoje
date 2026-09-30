"""Authentication endpoints (stubs)."""

from fastapi import APIRouter

from hoje.errors import not_implemented
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

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/state", response_model=AuthState, summary="Current authentication state")
async def auth_state() -> AuthState:
    raise not_implemented()


@router.post("/register", response_model=Me, status_code=201, summary="Register the first user")
async def auth_register(body: Register) -> Me:
    raise not_implemented()


@router.post("/login", response_model=LoginResponse, summary="Log in with email and password")
async def auth_login(body: LoginRequest) -> LoginResponse:
    raise not_implemented()


@router.post("/login/mfa", response_model=LoginResponse, summary="Complete login with a 2FA code")
async def auth_login_mfa(body: MfaRequest) -> LoginResponse:
    raise not_implemented()


@router.post("/logout", status_code=204, summary="Log out")
async def auth_logout() -> None:
    raise not_implemented()


@router.post("/password/forgot", status_code=202, summary="Request a password reset email")
async def auth_password_forgot(body: PasswordForgot) -> None:
    raise not_implemented()


@router.post("/password/reset", status_code=204, summary="Reset a password with a token")
async def auth_password_reset(body: PasswordReset) -> None:
    raise not_implemented()


@router.post("/password/change", status_code=204, summary="Change the current password")
async def auth_password_change(body: PasswordChange) -> None:
    raise not_implemented()


@router.post("/2fa/setup", response_model=TotpSetupResponse, summary="Begin TOTP enrolment")
async def auth_2fa_setup(body: TotpSetupRequest) -> TotpSetupResponse:
    raise not_implemented()


@router.post("/2fa/enable", response_model=RecoveryCodes, summary="Confirm TOTP enrolment")
async def auth_2fa_enable(body: TotpEnableRequest) -> RecoveryCodes:
    raise not_implemented()


@router.post("/2fa/disable", status_code=204, summary="Disable 2FA")
async def auth_2fa_disable(body: TotpConfirmRequest) -> None:
    raise not_implemented()


@router.post(
    "/2fa/recovery-codes", response_model=RecoveryCodes, summary="Regenerate recovery codes"
)
async def auth_2fa_recovery_codes(body: TotpConfirmRequest) -> RecoveryCodes:
    raise not_implemented()
