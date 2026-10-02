import pytest

from hoje.security import passwords


@pytest.mark.parametrize(
    "password", ["password123456", "1234567890", "qwertyuiop", "aaaaaaaaaaaa", "letmein12345"]
)
def test_weak_passwords_rejected_with_feedback(password: str) -> None:
    reason = passwords.password_weakness(password)
    assert reason is not None
    assert "easy to guess" in reason


def test_strong_passphrase_accepted() -> None:
    assert passwords.password_weakness("vT9#kQ2!mZp7wLx4") is None
    assert passwords.password_weakness("orbit lantern crescent velvet harbour") is None


def test_too_short_and_too_long() -> None:
    assert passwords.password_weakness("Sh0rt!") is not None
    assert passwords.password_weakness("x" * 257) is not None


def test_user_inputs_lower_the_score() -> None:
    assert passwords.password_weakness("ana.correia.lisboa", ["ana.correia.lisboa"]) is not None


def test_hash_round_trip_and_rehash_flag() -> None:
    hashed = passwords.hash_password_sync("correct horse battery")
    assert hashed.startswith("$argon2id$")
    assert "m=65536,t=3,p=4" in hashed
    assert passwords.verify_password_sync(hashed, "correct horse battery")
    assert not passwords.verify_password_sync(hashed, "wrong")
    assert not passwords.needs_rehash(hashed)


def test_invalid_hash_never_verifies() -> None:
    assert not passwords.verify_password_sync("$argon2id$v=19$m=19456,t=2,p=1$", "x")
    assert not passwords.verify_password_sync("not a hash", "x")


async def test_async_verify_unknown_account_is_false() -> None:
    assert await passwords.verify_password(None, "anything") is False


async def test_find_matching_hash() -> None:
    hashes = await passwords.hash_many(["AAAAAAAAAA", "BBBBBBBBBB"])
    candidates = [("first", hashes[0]), ("second", hashes[1])]
    assert await passwords.find_matching_hash(candidates, "BBBBBBBBBB") == "second"
    assert await passwords.find_matching_hash(candidates, "CCCCCCCCCC") is None
