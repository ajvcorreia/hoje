"""SQLAlchemy models. Importing this package registers every table on ``Base.metadata``."""

from hoje.db import Base
from hoje.models.auth import AuthThrottle, PasswordResetToken, RecoveryCode, Session, User
from hoje.models.backup import BackupRun
from hoje.models.calendar import Category, Event, EventInvite, Reminder, ReminderDelivery
from hoje.models.integration import FelizAnnivIntegration
from hoje.models.leave import Holiday, HolidayCalendar, LeavePolicy, NotificationLog
from hoje.models.todo import Todo

__all__ = [
    "AuthThrottle",
    "BackupRun",
    "Base",
    "Category",
    "Event",
    "EventInvite",
    "FelizAnnivIntegration",
    "Holiday",
    "HolidayCalendar",
    "LeavePolicy",
    "NotificationLog",
    "PasswordResetToken",
    "RecoveryCode",
    "Reminder",
    "ReminderDelivery",
    "Session",
    "Todo",
    "User",
]
