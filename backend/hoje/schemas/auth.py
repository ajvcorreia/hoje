"""Auth, account and settings schemas."""

import uuid
from datetime import datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from hoje.schemas.common import (
    DailySummaryTime,
    MaxEventsPerDay,
    Timezone,
    VerticalTextSize,
    WeekendDays,
)

NewPassword = Field(min_length=10, max_length=256)
ExistingPassword = Field(min_length=1, max_length=256)


class Me(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    timezone: str
    weekend_days: list[int]
    max_events_per_day: int
    vertical_text_size: int
    daily_summary_enabled: bool
    daily_summary_time: str  # "HH:MM" in `timezone`
    daily_summary_last_sent_at: datetime | None = None
    totp_enabled: bool
    last_category_id: uuid.UUID | None = None
    created_at: datetime

    @field_validator("daily_summary_time", mode="before")
    @classmethod
    def _time_as_text(cls, value: object) -> object:
        return value.strftime("%H:%M") if isinstance(value, time) else value


class MeUpdate(BaseModel):
    timezone: Timezone | None = None
    weekend_days: WeekendDays | None = None
    max_events_per_day: MaxEventsPerDay | None = None
    vertical_text_size: VerticalTextSize | None = None
    daily_summary_enabled: bool | None = None
    daily_summary_time: DailySummaryTime | None = None


class AuthState(BaseModel):
    registration_open: bool
    setup_token_required: bool
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
    setup_token: str | None = Field(default=None, max_length=256)


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


class EmailLogEntry(BaseModel):
    """One row of the current user's outgoing email log (never the body)."""

    model_config = ConfigDict(from_attributes=True)

    created_at: datetime
    kind: Literal["reminder", "password_reset", "test", "security", "daily_summary"]
    subject: str
    status: Literal["sent", "failed"]
    error: str | None = None
