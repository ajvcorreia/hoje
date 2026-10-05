"""SQLAlchemy models. Importing this package registers every table on ``Base.metadata``."""

from hoje.db import Base
from hoje.models.auth import AuthThrottle, PasswordResetToken, RecoveryCode, Session, User
from hoje.models.backup import BackupRun
from hoje.models.calendar import Category, Event, Reminder, ReminderDelivery
from hoje.models.integration import Birthday, FelizAnnivIntegration
from hoje.models.leave import Holiday, HolidayCalendar, LeavePolicy, NotificationLog

__all__ = [
    "AuthThrottle",
    "BackupRun",
    "Base",
    "Birthday",
    "Category",
    "Event",
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
    "User",
]
