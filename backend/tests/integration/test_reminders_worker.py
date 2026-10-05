"""Reminder scheduling and delivery against real Postgres with real commits.

Like ``test_realtime_sync.py`` these tests use their own engine and committed transactions
(the shared ``db_session`` fixture never commits) and delete everything they created. Time is
frozen with ``hoje.clock.now`` patched; the user lives in Europe/Lisbon (UTC+1 in October).
"""

import asyncio
import datetime as dt
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from hoje.api.deps import get_session_factory
from hoje.config import get_settings
from hoje.db import get_db
from hoje.main import create_app
from hoje.models import (
    Category,
    Event,
    NotificationLog,
    PasswordResetToken,
    Reminder,
    ReminderDelivery,
    User,
)
from hoje.models import Session as SessionRow
from hoje.security.tokens import hash_token
from hoje.services import housekeeping, reminders, sessions
from hoje.services.mailer import MemoryMailer, SendOutcome

pytestmark = pytest.mark.db

T0 = dt.datetime(2026, 10, 2, 12, 28, tzinfo=dt.UTC)  # 13:28 in Lisbon (Fri 2 Oct 2026)
DUE = dt.datetime(2026, 10, 2, 12, 30, tzinfo=dt.UTC)  # the default event starts at 13:30 Lisbon


def at(hour: int, minute: int = 0, day: int = 2) -> dt.datetime:
    return dt.datetime(2026, 10, day, hour, minute, tzinfo=dt.UTC)


@dataclass
class Live:
    sm: async_sessionmaker[AsyncSession]
    users: list[uuid.UUID] = field(default_factory=list)

    async def make_user(self, email: str | None = None) -> User:
        async with self.sm() as db:
            user = User(
                email=email or f"rem-{uuid.uuid4().hex[:10]}@example.com",
                password_hash="$argon2id$v=19$m=19456,t=2,p=1$",
                timezone="Europe/Lisbon",
                weekend_days=[6, 7],
            )
            db.add(user)
            await db.flush()
            db.add(Category(user_id=user.id, name="Work", colour="blue", icon=None, sort_order=0))
            await db.commit()
        self.users.append(user.id)
        return user

    async def make_event(
        self,
        user: User,
        *,
        title: str = "Team lunch",
        start: dt.date = dt.date(2026, 10, 2),
        start_time: dt.time | None = dt.time(13, 30),
        offsets: tuple[int, ...] = (0,),
        repeat: str = "none",
        notes: str | None = "SECRET NOTES",
    ) -> tuple[uuid.UUID, list[uuid.UUID]]:
        async with self.sm() as db:
            category = await db.scalar(select(Category).where(Category.user_id == user.id))
            assert category is not None
            event = Event(
                user_id=user.id,
                category_id=category.id,
                title=title,
                notes=notes,
                start_date=start,
                end_date=start,
                all_day=start_time is None,
                start_time=start_time,
                end_time=None if start_time is None else dt.time(14, 30),
                timezone="Europe/Lisbon",
                repeat=repeat,
            )
            db.add(event)
            await db.flush()
            rems = [Reminder(event_id=event.id, offset_minutes=o) for o in offsets]
            db.add_all(rems)
            await db.commit()
            return event.id, [r.id for r in rems]

    async def rows(self, event_id: uuid.UUID | None = None) -> list[ReminderDelivery]:
        async with self.sm() as db:
            stmt = (
                select(ReminderDelivery)
                .join(Reminder, Reminder.id == ReminderDelivery.reminder_id)
                .join(Event, Event.id == Reminder.event_id)
                .order_by(ReminderDelivery.due_at, ReminderDelivery.occurrence_date)
            )
            if event_id is not None:
                stmt = stmt.where(Reminder.event_id == event_id)
            else:
                stmt = stmt.where(Event.user_id.in_(self.users))
            return list((await db.scalars(stmt)).all())

    async def schedule(self, now: dt.datetime, horizon: dt.timedelta) -> int:
        async with self.sm() as db:
            created = await reminders.schedule(db, now, horizon)
            await db.commit()
        return created

    async def cycle(self, mailer, stop: asyncio.Event | None = None) -> reminders.CycleStats:
        return await reminders.run_cycle(self.sm, mailer, get_settings(), stop)

    def mailer(self) -> MemoryMailer:
        return MemoryMailer(session_factory=self.sm)

    async def sql(self, stmt) -> None:
        async with self.sm() as db:
            await db.execute(stmt)
            await db.commit()


class Flaky:
    """A mailer that answers from a script of outcomes (an Exception is raised)."""

    configured = True
    from_address = "hoje@example.com"

    def __init__(self, outcomes: list[SendOutcome | Exception]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[str | None] = []

    async def deliver(self, to, subject, text, html, *, kind, user_id, message_id=None):
        self.calls.append(message_id)
        outcome = self.outcomes.pop(0) if self.outcomes else SendOutcome(ok=True)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def send(self, *args, **kwargs) -> bool:
        return (await self.deliver(*args, **kwargs)).ok


UNDELIVERED = SendOutcome(ok=False, error="SMTPConnectError: refused", retryable=True)
AMBIGUOUS = SendOutcome(ok=False, error="SMTPReadTimeoutError: timed out", retryable=False)


@pytest_asyncio.fixture
async def live(db_url: str, _run_migrations: None, frozen_clock):
    frozen_clock.now = T0
    get_settings.cache_clear()
    engine = create_async_engine(db_url, poolclass=NullPool)
    state = Live(sm=async_sessionmaker(engine, expire_on_commit=False))
    try:
        yield state
    finally:
        async with state.sm() as db:
            await db.execute(
                delete(NotificationLog).where(NotificationLog.user_id.in_(state.users))
            )
            await db.execute(delete(Event).where(Event.user_id.in_(state.users)))
            await db.execute(delete(User).where(User.id.in_(state.users)))
            await db.commit()
        await engine.dispose()
        get_settings.cache_clear()


# ------------------------------------------------------------------ scheduling


async def test_schedule_creates_one_row_per_occurrence_even_when_run_twice(live: Live):
    user = await live.make_user()
    event_id, _ = await live.make_event(user)
    assert await live.schedule(T0, dt.timedelta(minutes=5)) == 1
    assert await live.schedule(T0, dt.timedelta(minutes=5)) == 0
    rows = await live.rows(event_id)
    assert len(rows) == 1
    assert (rows[0].status, rows[0].attempts, rows[0].due_at) == ("pending", 0, DUE)
    assert rows[0].occurrence_date == dt.date(2026, 10, 2)


async def test_schedule_ignores_rows_outside_the_window_and_deleted_events(live: Live):
    user = await live.make_user()
    soon, _ = await live.make_event(user)
    far, _ = await live.make_event(user, start=dt.date(2026, 11, 20))
    gone, _ = await live.make_event(user, title="Gone")
    await live.sql(update(Event).where(Event.id == gone).values(deleted_at=T0))
    assert await live.schedule(T0, dt.timedelta(minutes=5)) == 1
    assert len(await live.rows(soon)) == 1
    assert await live.rows(far) == [] and await live.rows(gone) == []


async def test_repeating_event_gets_a_delivery_per_occurrence(live: Live):
    user = await live.make_user()
    event_id, _ = await live.make_event(
        user, start=dt.date(2026, 8, 31), repeat="monthly", offsets=(0, 1440)
    )
    created = await live.schedule(T0, dt.timedelta(days=75))
    rows = await live.rows(event_id)
    # 30 Sep is already more than 24 h in the past; 31 Dec is beyond the horizon.
    assert created == len(rows) == 4  # 2 reminders x (31 Oct, 30 Nov)
    assert sorted({r.occurrence_date for r in rows}) == [
        dt.date(2026, 10, 31),
        dt.date(2026, 11, 30),
    ]
    assert await live.schedule(T0, dt.timedelta(days=75)) == 0


# ------------------------------------------------------------------ delivery


async def test_reminder_is_sent_once_with_html_text_and_log(live: Live, frozen_clock):
    user = await live.make_user()
    event_id, [reminder_id] = await live.make_event(user)
    mailer = live.mailer()
    assert (await live.cycle(mailer)).created == 1  # at 12:28, nothing due yet
    assert mailer.outbox == []
    frozen_clock.now = DUE
    stats = await live.cycle(mailer)
    assert stats.sent == 1
    await live.cycle(mailer)
    await live.cycle(mailer)
    assert len(mailer.outbox) == 1
    sent = mailer.outbox[0]
    assert sent.to == user.email and sent.kind == "reminder" and sent.user_id == user.id
    assert sent.subject == "Reminder: Team lunch · Fri 2 Oct, 13:30"
    assert sent.message_id == f"<reminder-{reminder_id}-2026-10-02@hoje>"
    assert sent.text.strip() and "<html" in sent.html.lower()
    for body in (sent.text, sent.html):
        assert "SECRET NOTES" not in body
        assert "Team lunch" in body and "Work" in body
    assert f"{get_settings().public_url}/" in sent.text
    [row] = await live.rows(event_id)
    assert (row.status, row.attempts, row.sent_at, row.last_error) == ("sent", 1, DUE, None)
    async with live.sm() as db:
        logged = (
            await db.scalars(select(NotificationLog).where(NotificationLog.user_id == user.id))
        ).all()
    assert [(n.kind, n.status, n.message_id) for n in logged] == [
        ("reminder", "sent", sent.message_id)
    ]


class SlowMailer(MemoryMailer):
    async def deliver(self, *args, **kwargs):
        await asyncio.sleep(0.01)
        return await super().deliver(*args, **kwargs)


async def test_two_concurrent_workers_send_each_reminder_once(live: Live, frozen_clock):
    user = await live.make_user()
    for i in range(25):
        await live.make_event(user, title=f"Event {i}")
    await live.schedule(T0, dt.timedelta(minutes=5))
    frozen_clock.now = DUE
    first, second = SlowMailer(live.sm), SlowMailer(live.sm)
    await asyncio.gather(live.cycle(first), live.cycle(second))
    ids = [m.message_id for m in first.outbox + second.outbox]
    assert len(ids) == len(set(ids)) == 25
    assert {r.status for r in await live.rows()} == {"sent"}


async def test_crashed_sending_row_is_failed_and_never_resent(live: Live, frozen_clock):
    user = await live.make_user()
    event_id, _ = await live.make_event(user)
    await live.schedule(T0, dt.timedelta(minutes=5))
    frozen_clock.now = DUE
    # Simulate a worker that committed `sending` and died before recording the outcome.
    await live.sql(
        update(ReminderDelivery)
        .where(ReminderDelivery.status == "pending")
        .values(status="sending", attempts=1, updated_at=DUE)
    )
    mailer = live.mailer()
    frozen_clock.now = DUE + dt.timedelta(minutes=9)
    await live.cycle(mailer)
    assert [r.status for r in await live.rows(event_id)] == ["sending"]
    frozen_clock.now = DUE + dt.timedelta(minutes=11)
    await live.cycle(mailer)
    [row] = await live.rows(event_id)
    assert row.status == "failed"
    assert row.last_error == "interrupted; not retried to avoid duplicates"
    frozen_clock.now = DUE + dt.timedelta(hours=2)
    await live.cycle(mailer)
    assert mailer.outbox == []
    assert [r.status for r in await live.rows(event_id)] == ["failed"]


async def test_clear_smtp_failures_retry_then_fail(live: Live, frozen_clock):
    user = await live.make_user()
    event_id, _ = await live.make_event(user)
    mailer = Flaky([UNDELIVERED] * 5)
    await live.schedule(T0, dt.timedelta(minutes=5))
    expected = [
        (DUE, dt.timedelta(minutes=1)),
        (at(12, 31), dt.timedelta(minutes=5)),
        (at(12, 36), dt.timedelta(minutes=30)),
        (at(13, 6), dt.timedelta(minutes=120)),
    ]
    for attempt, (when, delay) in enumerate(expected, start=1):
        frozen_clock.now = when
        await live.cycle(mailer)
        [row] = await live.rows(event_id)
        assert (row.status, row.attempts) == ("pending", attempt)
        assert row.next_attempt_at == when + delay
        assert row.last_error and "refused" in row.last_error
        frozen_clock.now = when + delay - dt.timedelta(seconds=1)
        await live.cycle(mailer)  # not yet time: no extra call
        assert len(mailer.calls) == attempt
    frozen_clock.now = at(15, 6)
    await live.cycle(mailer)
    [row] = await live.rows(event_id)
    assert (row.status, row.attempts, row.next_attempt_at) == ("failed", 5, None)
    assert len(mailer.calls) == 5 and len(set(mailer.calls)) == 1  # same Message-ID each time


async def test_retry_then_success(live: Live, frozen_clock):
    user = await live.make_user()
    event_id, _ = await live.make_event(user)
    mailer = Flaky([UNDELIVERED, SendOutcome(ok=True)])
    await live.schedule(T0, dt.timedelta(minutes=5))
    frozen_clock.now = DUE
    await live.cycle(mailer)
    frozen_clock.now = at(12, 31)
    await live.cycle(mailer)
    [row] = await live.rows(event_id)
    assert (row.status, row.attempts, row.last_error) == ("sent", 2, None)


@pytest.mark.parametrize("outcome", [AMBIGUOUS, RuntimeError("boom")])
async def test_ambiguous_errors_are_not_retried(live: Live, frozen_clock, outcome):
    user = await live.make_user()
    event_id, _ = await live.make_event(user)
    mailer = Flaky([outcome])
    await live.schedule(T0, dt.timedelta(minutes=5))
    frozen_clock.now = DUE
    await live.cycle(mailer)
    frozen_clock.now = DUE + dt.timedelta(hours=1)
    await live.cycle(mailer)
    [row] = await live.rows(event_id)
    assert (row.status, row.attempts) == ("failed", 1)
    assert len(mailer.calls) == 1


async def test_reminder_due_more_than_24_hours_ago_is_skipped(live: Live, frozen_clock):
    user = await live.make_user()
    event_id, [reminder_id] = await live.make_event(user)
    # The worker was down: the row exists but its due time is 25 h in the past.
    await live.sql(
        insert(ReminderDelivery).values(
            reminder_id=reminder_id,
            occurrence_date=dt.date(2026, 10, 2),
            due_at=DUE,
            status="pending",
            attempts=0,
            next_attempt_at=DUE,
        )
    )
    frozen_clock.now = DUE + dt.timedelta(hours=25)
    mailer = live.mailer()
    await live.cycle(mailer)
    [row] = await live.rows(event_id)
    assert row.status == "skipped" and mailer.outbox == []


async def test_claim_skips_a_row_that_is_late_even_if_housekeeping_did_not(live: Live):
    user = await live.make_user()
    event_id, [reminder_id] = await live.make_event(user)
    await live.sql(
        insert(ReminderDelivery).values(
            reminder_id=reminder_id,
            occurrence_date=dt.date(2026, 10, 2),
            due_at=DUE,
            status="pending",
            next_attempt_at=DUE,
        )
    )
    async with live.sm() as db:
        claims, examined = await reminders.claim_due(db, DUE + dt.timedelta(hours=24, minutes=1))
    assert claims == [] and examined == 1
    assert [r.status for r in await live.rows(event_id)] == ["skipped"]


async def test_event_deleted_before_it_is_due_is_not_sent(live: Live, frozen_clock):
    user = await live.make_user()
    event_id, _ = await live.make_event(user)
    mailer = live.mailer()
    await live.cycle(mailer)
    assert [r.status for r in await live.rows(event_id)] == ["pending"]
    await live.sql(update(Event).where(Event.id == event_id).values(deleted_at=T0))
    frozen_clock.now = DUE
    await live.cycle(mailer)
    [row] = await live.rows(event_id)
    assert (row.status, row.last_error) == ("skipped", "event deleted")
    assert mailer.outbox == []


async def test_event_moved_later_the_same_day_is_sent_at_the_new_time_only(
    live: Live, frozen_clock
):
    user = await live.make_user()
    event_id, _ = await live.make_event(user)
    mailer = live.mailer()
    await live.cycle(mailer)
    await live.sql(update(Event).where(Event.id == event_id).values(start_time=dt.time(16, 0)))
    frozen_clock.now = DUE
    await live.cycle(mailer)
    [row] = await live.rows(event_id)
    assert (row.status, row.due_at) == ("pending", at(15, 0))
    assert mailer.outbox == []
    frozen_clock.now = at(15, 0)
    await live.cycle(mailer)
    await live.cycle(mailer)
    assert [m.subject for m in mailer.outbox] == ["Reminder: Team lunch · Fri 2 Oct, 16:00"]
    assert [r.status for r in await live.rows(event_id)] == ["sent"]


async def test_event_moved_to_another_day_is_rescheduled(live: Live, frozen_clock):
    user = await live.make_user()
    event_id, _ = await live.make_event(user)
    mailer = live.mailer()
    await live.cycle(mailer)
    await live.sql(
        update(Event)
        .where(Event.id == event_id)
        .values(start_date=dt.date(2026, 10, 3), end_date=dt.date(2026, 10, 3))
    )
    frozen_clock.now = DUE
    await live.cycle(mailer)
    assert mailer.outbox == []
    statuses = {r.occurrence_date.day: r.status for r in await live.rows(event_id)}
    assert statuses == {2: "skipped"}
    frozen_clock.now = at(12, 28, day=3)
    await live.cycle(mailer)
    frozen_clock.now = at(12, 30, day=3)
    await live.cycle(mailer)
    await live.cycle(mailer)
    assert [m.subject for m in mailer.outbox] == ["Reminder: Team lunch · Sat 3 Oct, 13:30"]


async def test_unconfigured_smtp_leaves_rows_pending_without_burning_attempts(
    live: Live, frozen_clock
):
    user = await live.make_user()
    event_id, _ = await live.make_event(user)
    mailer = live.mailer()
    mailer.configured = False
    await live.cycle(mailer)
    frozen_clock.now = DUE
    stats = await live.cycle(mailer)
    assert stats.pending_unsent == 1 and stats.sent == 0
    [row] = await live.rows(event_id)
    assert (row.status, row.attempts) == ("pending", 0)
    mailer.configured = True  # SMTP gets configured later: the reminder goes out
    await live.cycle(mailer)
    assert len(mailer.outbox) == 1


async def test_shutdown_releases_unstarted_claims_without_burning_attempts(
    live: Live, frozen_clock
):
    user = await live.make_user()
    event_id, _ = await live.make_event(user)
    await live.schedule(T0, dt.timedelta(minutes=5))
    frozen_clock.now = DUE
    async with live.sm() as db:
        claims, _examined = await reminders.claim_due(db, DUE)
    assert [c.attempts for c in claims] == [1]
    async with live.sm() as db:
        await reminders.release(db, claims)
    [row] = await live.rows(event_id)
    assert (row.status, row.attempts) == ("pending", 0)


async def test_stop_before_the_cycle_sends_nothing(live: Live, frozen_clock):
    user = await live.make_user()
    event_id, _ = await live.make_event(user)
    await live.schedule(T0, dt.timedelta(minutes=5))
    frozen_clock.now = DUE
    stop = asyncio.Event()
    stop.set()
    mailer = live.mailer()
    await live.cycle(mailer, stop)
    assert mailer.outbox == []
    assert [r.status for r in await live.rows(event_id)] == ["pending"]


# ------------------------------------------------------------------ housekeeping


async def test_daily_housekeeping_purges_only_old_rows(live: Live):
    user = await live.make_user()
    old, _ = await live.make_event(user, title="Old")
    fresh, _ = await live.make_event(user, title="Fresh")
    _kept, [kept_reminder] = await live.make_event(user, title="Live")
    now = dt.datetime(2026, 10, 2, 12, 0, tzinfo=dt.UTC)
    day = dt.timedelta(days=1)
    await live.sql(update(Event).where(Event.id == old).values(deleted_at=now - 31 * day))
    await live.sql(update(Event).where(Event.id == fresh).values(deleted_at=now - 29 * day))
    await live.sql(
        insert(ReminderDelivery).values(
            reminder_id=kept_reminder,
            occurrence_date=dt.date(2026, 3, 1),
            due_at=now - 181 * day,
            status="sent",
        )
    )
    async with live.sm() as db:
        for age, subject in ((181, "Old log"), (179, "Fresh log")):
            db.add(
                NotificationLog(
                    user_id=user.id,
                    kind="test",
                    to_address=user.email,
                    subject=subject,
                    status="sent",
                    created_at=now - age * day,
                )
            )
        await db.commit()
    async with live.sm() as db:
        db.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=hash_token("x"),
                expires_at=now - 8 * day,
                created_at=now - 8 * day,
            )
        )
        await sessions.create(db, user.id, stage="active", ip=None, user_agent=None)
        await db.execute(
            update(SessionRow)
            .where(SessionRow.user_id == user.id)
            .values(absolute_expires_at=now - day)
        )
        await db.commit()
    async with live.sm() as db:
        removed = await housekeeping.run_daily(db, now)
        await db.commit()
    assert removed["events"] >= 1 and removed["reminder_deliveries"] == 1
    assert removed["reset_links"] >= 1 and removed["sessions"] >= 1
    assert removed["notification_log_rows"] == 1
    async with live.sm() as db:
        titles = set((await db.scalars(select(Event.title).where(Event.user_id == user.id))).all())
        assert titles == {"Fresh", "Live"}
        subjects = set(
            (
                await db.scalars(
                    select(NotificationLog.subject).where(NotificationLog.user_id == user.id)
                )
            ).all()
        )
        assert subjects == {"Fresh log"}
        assert not await db.scalar(
            select(func.count())
            .select_from(PasswordResetToken)
            .where(PasswordResetToken.user_id == user.id)
        )


# ------------------------------------------------------------------ /settings/email/log


async def test_email_log_returns_only_the_current_users_rows(live: Live, monkeypatch):
    monkeypatch.setenv("HOJE_INSECURE_COOKIES", "true")
    get_settings.cache_clear()
    alice, bob = await live.make_user(), await live.make_user()
    async with live.sm() as db:
        base = dt.datetime(2026, 10, 1, tzinfo=dt.UTC)
        for i in range(25):
            db.add(
                NotificationLog(
                    user_id=alice.id,
                    kind="reminder",
                    to_address=alice.email,
                    subject=f"Alice {i}",
                    status="failed" if i == 24 else "sent",
                    error="refused" if i == 24 else None,
                    created_at=base + dt.timedelta(minutes=i),
                )
            )
        db.add(
            NotificationLog(
                user_id=bob.id, kind="test", to_address=bob.email, subject="Bob", status="sent"
            )
        )
        raw, _ = await sessions.create(db, alice.id, stage="active", ip=None, user_agent=None)
        await db.commit()

    app = create_app()

    async def override_db() -> AsyncIterator[AsyncSession]:
        async with live.sm() as session:
            yield session

    @asynccontextmanager
    async def factory() -> AsyncIterator[AsyncSession]:
        async with live.sm() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_session_factory] = lambda: factory
    cookies = {"Cookie": f"{sessions.COOKIE_NAME_INSECURE}={raw}"}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/settings/email/log", headers=cookies)
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 20
        assert body[0]["subject"] == "Alice 24" and body[0]["status"] == "failed"
        assert body[0]["error"] == "refused"
        assert all(row["subject"].startswith("Alice") for row in body)
        assert set(body[0]) == {"created_at", "kind", "subject", "status", "error"}
        few = await c.get("/api/v1/settings/email/log", params={"limit": 3}, headers=cookies)
        assert [r["subject"] for r in few.json()] == ["Alice 24", "Alice 23", "Alice 22"]
        assert (await c.get("/api/v1/settings/email/log")).status_code == 401
    app.dependency_overrides.clear()
