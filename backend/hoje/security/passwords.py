"""Password hashing (argon2id) and strength policy (zxcvbn).

Hashing is CPU and memory heavy on purpose, so it always runs in a worker thread and at most
``MAX_CONCURRENT_HASHES`` at a time (each uses 64 MiB; the API container has 256 MiB).
"""

import asyncio
import functools
from collections.abc import Callable, Sequence
from typing import Any

import anyio.to_thread
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from zxcvbn import zxcvbn

MIN_LENGTH = 10
MAX_LENGTH = 256
MIN_SCORE = 3
MAX_CONCURRENT_HASHES = 2
# zxcvbn's running time grows quickly with input length; the first 100 characters are plenty
# to judge strength (a weak prefix is weak, a strong one is strong enough).
_ZXCVBN_MAX_CHARS = 100

# argon2-cffi defaults follow RFC 9106 "low memory": t=3, m=64 MiB, p=4, argon2id.
_hasher = PasswordHasher()
_semaphore: asyncio.Semaphore | None = None
_semaphore_loop: asyncio.AbstractEventLoop | None = None


def _limiter() -> asyncio.Semaphore:
    """A semaphore bound to the running loop (tests may use several loops)."""
    global _semaphore, _semaphore_loop
    loop = asyncio.get_running_loop()
    if _semaphore is None or _semaphore_loop is not loop:
        _semaphore = asyncio.Semaphore(MAX_CONCURRENT_HASHES)
        _semaphore_loop = loop
    return _semaphore


async def _run(func: Callable[..., Any], *args: Any) -> Any:
    async with _limiter():
        return await anyio.to_thread.run_sync(func, *args)


# --- synchronous primitives (used inside worker threads and by unit tests) -------------------


def hash_password_sync(password: str) -> str:
    return _hasher.hash(password)


def verify_password_sync(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return False


@functools.cache
def _dummy_hash() -> str:
    return _hasher.hash("hoje-timing-equaliser-not-a-real-password")


def password_weakness(password: str, user_inputs: Sequence[str] = ()) -> str | None:
    """Return a human-readable reason if ``password`` violates the policy, else ``None``."""
    if len(password) < MIN_LENGTH:
        return f"Use at least {MIN_LENGTH} characters."
    if len(password) > MAX_LENGTH:
        return f"Use at most {MAX_LENGTH} characters."
    result = zxcvbn(password[:_ZXCVBN_MAX_CHARS], user_inputs=[u for u in user_inputs if u])
    if result["score"] >= MIN_SCORE:
        return None
    feedback = result.get("feedback") or {}
    parts = ["This password is too easy to guess."]
    warning = (feedback.get("warning") or "").strip()
    if warning:
        parts.append(warning.rstrip(".") + ".")
    parts.extend(s.strip() for s in feedback.get("suggestions") or [] if s.strip())
    if not warning and not feedback.get("suggestions"):
        parts.append("Try a longer passphrase of several unrelated words.")
    return " ".join(parts)


def _first_match(candidates: Sequence[tuple[object, str]], password: str) -> object | None:
    found = None
    for key, password_hash in candidates:
        if verify_password_sync(password_hash, password) and found is None:
            found = key
    return found


# --- async API --------------------------------------------------------------------------------


async def hash_password(password: str) -> str:
    return await _run(hash_password_sync, password)


async def hash_many(passwords: Sequence[str]) -> list[str]:
    """Hash several secrets in one worker-thread call (one semaphore slot)."""
    return await _run(lambda: [hash_password_sync(p) for p in passwords])


async def verify_password(password_hash: str | None, password: str) -> bool:
    """Verify a password; with ``None`` (unknown account) burn the same time and return False."""
    if password_hash is None:
        await _run(verify_password_sync, _dummy_hash(), password)
        return False
    return await _run(verify_password_sync, password_hash, password)


async def find_matching_hash[K](candidates: Sequence[tuple[K, str]], secret: str) -> K | None:
    """Return the key whose hash matches ``secret``. Checks every candidate (no early exit)."""
    return await _run(_first_match, candidates, secret)


async def password_weakness_async(password: str, user_inputs: Sequence[str] = ()) -> str | None:
    return await anyio.to_thread.run_sync(password_weakness, password, user_inputs)
