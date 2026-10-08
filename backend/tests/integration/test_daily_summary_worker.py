"""Daily summary scheduling and delivery against real Postgres with real commits.

Own engine and committed transactions like ``test_reminders_worker.py``; time is frozen with
``hoje.clock.now`` patched. The user lives in Europe/Lisbon (UTC+1 on 8 October 2026) and wants
the summary at 07:00 local, which is 06:00 UTC.
"""

import asyncio
import datetime as dt
import uuid
from dataclasses import dataclass, field

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from hoje import clock
from hoje.config import get_settings
from hoje.models import (
    Birthday,
    Category,
    Event,
    Holiday,
    HolidayCalendar,
    NotificationLog,
    User,
)
from hoje.services import daily_summary
from hoje.services.mailer import MemoryMailer, SendOutcome

pytestmark = pytest.mark.db


def at(hour: int, minute: int = 0, day: int = 8) -> dt.datetime:
    return dt.datetime(2026, 10, day, hour, minute, tzinfo=dt.UTC)


SEND = at(6, 0)  # 07:00 in Lisbon on Thu 8 Oct 2026
TODAY = dt.date(2026, 10, 8)

UNDELIVERED = SendOutcome(ok=False, error="SMTPConnectError: refused", retryable=True)
AMBIGUOUS = SendOutcome(ok=False, error="SMTPReadTimeoutError: timed out", retryable=False)


class Flaky(MemoryMailer):
    """Answers from a script of outcomes (an Exception is raised); success records the message."""

    def __init__(self, session_factory, outcomes: list[SendOutcome | Exception]) -> None:
        super().__init__(session_factory)
        self.outcomes = list(outcomes)
        self.calls = 0

    async def deliver(self, *args, **kwargs):
        self.calls += 1
        outcome = self.outcomes.pop(0) if self.outcomes else None
        if isinstance(outcome, Exception):
            raise outcome
        if outcome is None:
            return await super().deliver(*args, **kwargs)
        # Failures write the delivery log too, like the real mailer.
        async with self._factory() as db:
            db.add(
                NotificationLog(
                    user_id=kwargs["user_id"],
                    kind=kwargs["kind"],
                    to_address=args[0],
                    subject=args[1],
                    status="failed",
                    error=outcome.error,
                    created_at=clock.now(),  # the frozen clock, which the retry back-off reads
                )
            )
            await db.commit()
        return outcome


class SlowMailer(MemoryMailer):
    async def deliver(self, *args, **kwargs):
        await asyncio.sleep(0.05)
        return await super().deliver(*args, **kwargs)


@dataclass
class Live:
    sm: async_sessionmaker[AsyncSession]
    users: list[uuid.UUID] = field(default_factory=list)

    async def make_user(
        self,
        *,
        enabled: bool = True,
        send_time: dt.time = dt.time(7, 0),
        tz: str = "Europe/Lisbon",
        last_sent: dt.datetime | None = None,
    ) -> User:
        async with self.sm() as db:
            user = User(
                email=f"sum-{uuid.uuid4().hex[:10]}@example.com",
                password_hash="$argon2id$v=19$m=19456,t=2,p=1$",
                timezone=tz,
                weekend_days=[6, 7],
                daily_summary_enabled=enabled,
                daily_summary_time=send_time,
                daily_summary_last_sent_at=last_sent,
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
        title: str = "Team lunch",
        start: dt.date = TODAY,
        stamp: dt.datetime | None = None,
        **extra,
    ) -> uuid.UUID:
        stamp = stamp or at(0, 0, day=1)
        async with self.sm() as db:
            category = await db.scalar(select(Category).where(Category.user_id == user.id))
            assert category is not None
            event = Event(
                user_id=user.id,
                category_id=category.id,
                title=title,
                start_date=start,
                end_date=start,
                all_day=True,
                timezone="Europe/Lisbon",
                created_at=stamp,
                updated_at=stamp,
                **extra,
            )
            db.add(event)
            await db.commit()
            return event.id

    async def user_row(self, user: User) -> User:
        async with self.sm() as db:
            row = await db.scalar(select(User).where(User.id == user.id))
            assert row is not None
            return row

    async def run(self, mailer) -> daily_summary.DueStats:
        return await daily_summary.run_due(self.sm, mailer, get_settings())

    def mailer(self) -> MemoryMailer:
        return MemoryMailer(session_factory=self.sm)

    async def log_rows(self, user: User) -> list[tuple[str, str]]:
        async with self.sm() as db:
            rows = await db.execute(
                select(NotificationLog.kind, NotificationLog.status).where(
                    NotificationLog.user_id == user.id
                )
            )
            return sorted((kind, status) for kind, status in rows)


@pytest_asyncio.fixture
async def live(db_url: str, _run_migrations: None, frozen_clock):
    frozen_clock.now = at(5, 59)
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
            await db.execute(delete(Birthday).where(Birthday.user_id.in_(state.users)))
            await db.execute(
                delete(HolidayCalendar).where(HolidayCalendar.user_id.in_(state.users))
            )
            await db.execute(delete(User).where(User.id.in_(state.users)))
            await db.commit()
        await engine.dispose()
        get_settings.cache_clear()


async def test_sent_once_at_the_local_send_time_and_marked(live: Live, frozen_clock):
    user = await live.make_user()
    await live.make_event(user)
    mailer = live.mailer()

    await live.run(mailer)  # 06:59 in Lisbon: not yet
    assert mailer.outbox == []

    frozen_clock.now = SEND
    stats = await live.run(mailer)
    assert (stats.sent, stats.skipped_empty) == (1, 0)
    for minute in (1, 30, 600):
        frozen_clock.now = SEND + dt.timedelta(minutes=minute)
        await live.run(mailer)
    assert len(mailer.outbox) == 1
    sent = mailer.outbox[0]
    assert (sent.to, sent.kind, sent.user_id) == (user.email, "daily_summary", user.id)
    assert sent.subject == "Hoje — Thursday 8 October: 1 event today"
    assert "Team lunch" in sent.text and "Team lunch" in sent.html
    assert (await live.user_row(user)).daily_summary_last_sent_at == SEND
    assert await live.log_rows(user) == [("daily_summary", "sent")]


async def test_a_missed_window_is_still_sent_later_the_same_day(live: Live, frozen_clock):
    user = await live.make_user()
    await live.make_event(user)
    mailer = live.mailer()
    frozen_clock.now = at(18, 30)  # worker was down all morning
    await live.run(mailer)
    assert len(mailer.outbox) == 1


async def test_next_day_sends_again_with_only_the_changes_since_the_last_summary(
    live: Live, frozen_clock
):
    user = await live.make_user()
    old = await live.make_event(user, "Old news", stamp=at(0, 0, day=1))
    mailer = live.mailer()
    frozen_clock.now = SEND
    await live.run(mailer)
    assert "Old news" in mailer.outbox[0].text  # first summary: Today section
    assert "Old news" not in mailer.outbox[0].text.split("TODAY")[0]  # not under "changes"

    await live.make_event(user, "Fresh", start=dt.date(2026, 10, 9), stamp=at(9, 0))
    async with live.sm() as db:
        await db.execute(update(Event).where(Event.id == old).values(updated_at=at(10, 0)))
        await db.commit()
    frozen_clock.now = at(6, 0, day=9)
    await live.run(mailer)
    assert len(mailer.outbox) == 2
    second = mailer.outbox[1].text
    assert "CHANGES SINCE THU 8 OCT, 07:00" in second
    assert "Added: Fresh" in second and "Changed: Old news" in second


async def test_changes_from_before_the_previous_summary_are_not_repeated(live: Live, frozen_clock):
    user = await live.make_user(last_sent=SEND)
    await live.make_event(user, "Seen", start=dt.date(2026, 10, 20), stamp=at(5, 0))
    await live.make_event(user, "Unseen", start=dt.date(2026, 10, 21), stamp=at(8, 0))
    mailer = live.mailer()
    frozen_clock.now = at(6, 0, day=9)
    await live.run(mailer)
    [sent] = mailer.outbox
    assert "Unseen" in sent.text and "Seen" not in sent.text.replace("Unseen", "")


async def test_an_empty_day_sends_nothing_but_is_handled(live: Live, frozen_clock):
    user = await live.make_user()
    mailer = live.mailer()
    frozen_clock.now = SEND
    stats = await live.run(mailer)
    assert (stats.sent, stats.skipped_empty) == (0, 1)
    assert mailer.outbox == []
    assert (await live.user_row(user)).daily_summary_last_sent_at == SEND
    # An event added later the same day does not trigger a second attempt.
    await live.make_event(user, "Late addition", stamp=at(9, 0))
    frozen_clock.now = at(10, 0)
    await live.run(mailer)
    assert mailer.outbox == []


async def test_birthdays_and_holidays_alone_make_a_summary(live: Live, frozen_clock):
    user = await live.make_user()
    async with live.sm() as db:
        db.add(
            Birthday(
                user_id=user.id,
                external_id="x1",
                name="Bea Silva",
                birth_month=10,
                birth_day=8,
                birth_year=1990,
            )
        )
        calendar = HolidayCalendar(
            user_id=user.id, code="pt", name="Portugal", enabled=True, colour="green"
        )
        db.add(calendar)
        await db.flush()
        db.add(
            Holiday(
                calendar_id=calendar.id,
                date=TODAY,
                name="Republic Day",
                is_non_working=True,
                source="bundled",
            )
        )
        await db.commit()
    mailer = live.mailer()
    frozen_clock.now = SEND
    await live.run(mailer)
    [sent] = mailer.outbox
    assert "Bea Silva" in sent.text and "(36)" in sent.text
    assert "Republic Day (Portugal, non-working day)" in sent.text


async def test_disabled_users_and_unconfigured_mail_send_and_mark_nothing(live: Live, frozen_clock):
    off = await live.make_user(enabled=False)
    on = await live.make_user()
    for user in (off, on):
        await live.make_event(user)
    mailer = live.mailer()
    mailer.configured = False
    frozen_clock.now = SEND
    await live.run(mailer)
    assert mailer.outbox == []
    assert (await live.user_row(on)).daily_summary_last_sent_at is None

    mailer.configured = True  # mail starts working later the same day: it goes out then
    frozen_clock.now = at(12, 0)
    await live.run(mailer)
    assert [m.user_id for m in mailer.outbox] == [on.id]
    assert (await live.user_row(off)).daily_summary_last_sent_at is None


async def test_each_user_is_judged_in_their_own_time_zone(live: Live, frozen_clock):
    lisbon = await live.make_user()
    dubai = await live.make_user(tz="Asia/Dubai")  # 07:00 there is 03:00 UTC
    for user in (lisbon, dubai):
        await live.make_event(user)
    mailer = live.mailer()
    frozen_clock.now = at(3, 0)
    await live.run(mailer)
    assert [m.user_id for m in mailer.outbox] == [dubai.id]
    frozen_clock.now = SEND
    await live.run(mailer)
    assert {m.user_id for m in mailer.outbox} == {dubai.id, lisbon.id}
    assert len(mailer.outbox) == 2


async def test_clear_failure_is_retried_later_and_never_marked(live: Live, frozen_clock):
    user = await live.make_user()
    await live.make_event(user)
    mailer = Flaky(live.sm, [UNDELIVERED])
    frozen_clock.now = SEND
    stats = await live.run(mailer)
    assert (stats.sent, stats.retry_later) == (0, 1)
    assert (await live.user_row(user)).daily_summary_last_sent_at is None

    frozen_clock.now = SEND + dt.timedelta(minutes=4)
    await live.run(mailer)  # still inside the 5 minute back-off
    assert mailer.calls == 1

    frozen_clock.now = SEND + dt.timedelta(minutes=6)
    stats = await live.run(mailer)
    assert stats.sent == 1 and mailer.calls == 2 and len(mailer.outbox) == 1
    assert (await live.user_row(user)).daily_summary_last_sent_at == SEND + dt.timedelta(minutes=6)
    assert await live.log_rows(user) == [("daily_summary", "failed"), ("daily_summary", "sent")]


async def test_retries_stop_after_five_failures_that_day(live: Live, frozen_clock):
    user = await live.make_user()
    await live.make_event(user)
    mailer = Flaky(live.sm, [UNDELIVERED] * 20)
    for i in range(12):
        frozen_clock.now = SEND + dt.timedelta(minutes=6 * i)
        await live.run(mailer)
    assert mailer.calls == daily_summary.MAX_FAILURES_PER_DAY
    assert (await live.user_row(user)).daily_summary_last_sent_at is None


async def test_ambiguous_failure_is_not_retried(live: Live, frozen_clock):
    user = await live.make_user()
    await live.make_event(user)
    mailer = Flaky(live.sm, [AMBIGUOUS])
    frozen_clock.now = SEND
    stats = await live.run(mailer)
    assert stats.failed == 1
    frozen_clock.now = at(9, 0)
    await live.run(mailer)
    assert mailer.calls == 1 and mailer.outbox == []
    assert (await live.user_row(user)).daily_summary_last_sent_at == SEND


async def test_an_exception_in_the_mailer_does_not_stop_other_users(live: Live, frozen_clock):
    broken = await live.make_user()
    healthy = await live.make_user()
    for user in (broken, healthy):
        await live.make_event(user)
    mailer = Flaky(live.sm, [RuntimeError("boom")])
    frozen_clock.now = SEND
    await live.run(mailer)
    assert mailer.calls == 2 and len(mailer.outbox) == 1
    for user in (broken, healthy):  # the one that raised is never resent either
        assert (await live.user_row(user)).daily_summary_last_sent_at == SEND


async def test_two_workers_at_once_send_one_email(live: Live, frozen_clock):
    user = await live.make_user()
    await live.make_event(user)
    first, second = SlowMailer(live.sm), SlowMailer(live.sm)
    frozen_clock.now = SEND
    await asyncio.gather(live.run(first), live.run(second))
    assert len(first.outbox) + len(second.outbox) == 1
    async with live.sm() as db:
        count = await db.scalar(
            select(func.count())
            .select_from(NotificationLog)
            .where(NotificationLog.user_id == user.id)
        )
    assert count == 1
