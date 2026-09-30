"""Test database constraints and domain rules."""

from datetime import UTC, date, datetime

import pytest
import sqlalchemy.exc
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from hoje.models.auth import User
from hoje.models.calendar import Category, Event, Reminder, ReminderDelivery
from hoje.models.leave import LeavePolicy

pytestmark = pytest.mark.db


class TestEmailUniqueness:
    @pytest.mark.asyncio
    async def test_email_is_citext_unique(self, db_session: AsyncSession) -> None:
        """Verify that user email is case-insensitively unique (citext)."""
        # Argon2 hash (test fixture, not a password)
        ph = "$argon2id$v=19$m=19456,t=2,p=1$"
        user1 = User(email="Test@Example.com", password_hash=ph, timezone="UTC")
        db_session.add(user1)
        await db_session.flush()

        # Same email in different case should fail
        user2 = User(email="test@example.com", password_hash=ph, timezone="UTC")
        db_session.add(user2)

        with pytest.raises(sqlalchemy.exc.IntegrityError):
            await db_session.flush()


class TestEventDateConstraints:
    @pytest.mark.asyncio
    async def test_event_end_date_before_start_date_rejected(
        self, db_session: AsyncSession, make_user
    ) -> None:
        """Verify that events with end_date < start_date are rejected."""
        user = await make_user()
        # Create a category for the user
        category = Category(
            user_id=user.id,
            name="Work",
            colour="blue",
            sort_order=1,
        )
        db_session.add(category)
        await db_session.flush()

        # Try to create an event with end_date < start_date
        bad_event = Event(
            user_id=user.id,
            category_id=category.id,
            title="Bad Event",
            start_date=date(2024, 1, 10),
            end_date=date(2024, 1, 5),  # Before start date
            timezone="UTC",
        )
        db_session.add(bad_event)

        with pytest.raises(sqlalchemy.exc.IntegrityError):
            await db_session.flush()


class TestEventRepeatConstraint:
    @pytest.mark.asyncio
    async def test_event_repeat_must_be_valid_value(
        self, db_session: AsyncSession, make_user
    ) -> None:
        """Verify that event repeat must be one of: none, monthly, yearly."""
        user = await make_user()
        category = Category(
            user_id=user.id,
            name="Work",
            colour="blue",
            sort_order=1,
        )
        db_session.add(category)
        await db_session.flush()

        # Try to create an event with invalid repeat value
        bad_event = Event(
            user_id=user.id,
            category_id=category.id,
            title="Event",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 1),
            timezone="UTC",
            repeat="weekly",  # Invalid value
        )
        db_session.add(bad_event)

        with pytest.raises(sqlalchemy.exc.IntegrityError):
            await db_session.flush()


class TestCategoryColourConstraint:
    @pytest.mark.asyncio
    async def test_category_colour_must_be_palette_key(
        self, db_session: AsyncSession, make_user
    ) -> None:
        """Verify that category colour must be a valid palette key."""
        user = await make_user()

        bad_category = Category(
            user_id=user.id,
            name="Work",
            colour="invalidcolor",  # Not in palette
            sort_order=1,
        )
        db_session.add(bad_category)

        with pytest.raises(sqlalchemy.exc.IntegrityError):
            await db_session.flush()

    @pytest.mark.asyncio
    async def test_category_colour_valid_palette_key(
        self, db_session: AsyncSession, make_user
    ) -> None:
        """Verify that valid palette keys are accepted."""
        user = await make_user()

        category = Category(
            user_id=user.id,
            name="Work",
            colour="blue",  # Valid palette key
            sort_order=1,
        )
        db_session.add(category)
        await db_session.flush()

        assert category.id is not None


class TestCategoryNameUniqueness:
    @pytest.mark.asyncio
    async def test_category_names_unique_per_user_case_insensitively(
        self, db_session: AsyncSession, make_user
    ) -> None:
        """Verify category names are unique per user case-insensitively among non-deleted."""
        user = await make_user()

        cat1 = Category(user_id=user.id, name="Work", colour="blue", sort_order=1)
        db_session.add(cat1)
        await db_session.flush()

        # Try to create another category with same name (different case) for same user
        cat2 = Category(user_id=user.id, name="work", colour="red", sort_order=2)
        db_session.add(cat2)

        with pytest.raises(sqlalchemy.exc.IntegrityError):
            await db_session.flush()

    @pytest.mark.asyncio
    async def test_soft_deleted_category_name_can_be_reused(
        self, db_session: AsyncSession, make_user
    ) -> None:
        """Verify that a soft-deleted category's name can be reused by same user."""
        user = await make_user()

        # Create a category
        cat1 = Category(user_id=user.id, name="Work", colour="blue", sort_order=1)
        db_session.add(cat1)
        await db_session.flush()

        # Soft-delete it
        cat1.deleted_at = datetime.now(UTC)
        await db_session.flush()

        # Should be able to create a new category with the same name
        cat2 = Category(user_id=user.id, name="Work", colour="red", sort_order=2)
        db_session.add(cat2)
        await db_session.flush()

        assert cat2.id is not None
        assert cat2.id != cat1.id


class TestReminderDeliveryUniqueness:
    @pytest.mark.asyncio
    async def test_reminder_delivery_unique_per_occurrence_date(
        self, db_session: AsyncSession, make_user
    ) -> None:
        """Verify reminder_deliveries (reminder_id, occurrence_date) is unique."""
        user = await make_user()
        category = Category(user_id=user.id, name="Work", colour="blue", sort_order=1)
        db_session.add(category)
        await db_session.flush()

        event = Event(
            user_id=user.id,
            category_id=category.id,
            title="Meeting",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 1),
            timezone="UTC",
        )
        db_session.add(event)
        await db_session.flush()

        reminder = Reminder(event_id=event.id, offset_minutes=15)
        db_session.add(reminder)
        await db_session.flush()

        # Create a reminder delivery
        delivery1 = ReminderDelivery(
            reminder_id=reminder.id,
            occurrence_date=date(2024, 1, 1),
            due_at=datetime(2024, 1, 1, 12, 45, tzinfo=UTC),
            status="pending",
        )
        db_session.add(delivery1)
        await db_session.flush()

        # Try to create another with same reminder_id and occurrence_date
        delivery2 = ReminderDelivery(
            reminder_id=reminder.id,
            occurrence_date=date(2024, 1, 1),
            due_at=datetime(2024, 1, 1, 12, 50, tzinfo=UTC),
            status="pending",
        )
        db_session.add(delivery2)

        with pytest.raises(sqlalchemy.exc.IntegrityError):
            await db_session.flush()


class TestLeavePolicyUniqueness:
    @pytest.mark.asyncio
    async def test_leave_policy_unique_per_user_year(
        self, db_session: AsyncSession, make_user
    ) -> None:
        """Verify leave_policies (user_id, year) is unique."""
        user = await make_user()

        policy1 = LeavePolicy(user_id=user.id, year=2024, allowance_days=20)
        db_session.add(policy1)
        await db_session.flush()

        # Try to create another policy for the same user and year
        policy2 = LeavePolicy(user_id=user.id, year=2024, allowance_days=25)
        db_session.add(policy2)

        with pytest.raises(sqlalchemy.exc.IntegrityError):
            await db_session.flush()


class TestCascadeDelete:
    @pytest.mark.asyncio
    async def test_delete_user_cascades_to_categories_and_events(
        self, db_session: AsyncSession, make_user
    ) -> None:
        """Verify that deleting a user cascades to its categories and events."""
        user = await make_user("cascade@test.com")

        # Create category
        category = Category(user_id=user.id, name="Work", colour="blue", sort_order=1)
        db_session.add(category)
        await db_session.flush()

        # Create event
        event = Event(
            user_id=user.id,
            category_id=category.id,
            title="Meeting",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 1),
            timezone="UTC",
        )
        db_session.add(event)
        await db_session.flush()

        category_id = category.id
        event_id = event.id

        # Delete the user
        await db_session.delete(user)
        await db_session.flush()

        # Verify category and event are gone
        result = await db_session.execute(
            text("SELECT id FROM categories WHERE id = :cat_id"),
            {"cat_id": str(category_id)},
        )
        assert result.scalar() is None

        result = await db_session.execute(
            text("SELECT id FROM events WHERE id = :evt_id"),
            {"evt_id": str(event_id)},
        )
        assert result.scalar() is None
