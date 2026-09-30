"""Auth, account and settings schemas."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from hoje.schemas.common import Timezone, WeekendDays

NewPassword = Field(min_length=10, max_length=256)
ExistingPassword = Field(min_length=1, max_length=256)


class Me(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    timezone: str
    weekend_days: list[int]
    totp_enabled: bool
    last_category_id: uuid.UUID | None = None
    created_at: datetime


class MeUpdate(BaseModel):
    timezone: Timezone | None = None
    weekend_days: WeekendDays | None = None


class AuthState(BaseModel):
    registration_open: bool
    authenticated: bool
    stage: Literal["mfa_pending", "active"] | None = None
    csrf_token: str | None = None
    user: Me | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = ExistingPassword


class LoginResponse(BaseModel):
    status: Literal["ok", "mfa_required"]


class MfaRequest(BaseModel):
    """A 6-digit TOTP code or a recovery code (xxxxx-xxxxx)."""

    code: str = Field(min_length=6, max_length=32)


class Register(BaseModel):
    email: EmailStr
    password: str = NewPassword


class PasswordForgot(BaseModel):
    email: EmailStr


class PasswordReset(BaseModel):
    token: str = Field(min_length=1, max_length=256)
    new_password: str = NewPassword


class PasswordChange(BaseModel):
    current_password: str = ExistingPassword
    new_password: str = NewPassword


class TotpSetupRequest(BaseModel):
    password: str = ExistingPassword


class TotpSetupResponse(BaseModel):
    otpauth_uri: str
    secret: str
    qr_svg: str


class TotpEnableRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class TotpConfirmRequest(BaseModel):
    """Password plus a TOTP or recovery code, for disabling 2FA or regenerating codes."""

    password: str = ExistingPassword
    code: str = Field(min_length=6, max_length=32)


class RecoveryCodes(BaseModel):
    recovery_codes: list[str] = Field(min_length=10, max_length=10)


class EmailSettings(BaseModel):
    configured: bool
    from_address: str | None = None
