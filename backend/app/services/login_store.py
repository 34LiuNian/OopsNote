"""Login attempt tracking and brute-force protection."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import NamedTuple


class LoginAttemptInfo(NamedTuple):
    """Information about login attempts."""

    count: int
    last_attempt: datetime
    locked_until: datetime | None = None


class LoginAttemptStore:
    """Thread-safe store for tracking login attempts."""

    def __init__(self) -> None:
        self._attempts: dict[str, LoginAttemptInfo] = {}
        self._lock = threading.Lock()

    def record_failed_attempt(
        self,
        username: str,
        max_attempts: int,
        lockout_minutes: int,
    ) -> LoginAttemptInfo:
        """
        Record a failed login attempt.

        Returns:
            LoginAttemptInfo with current status
        """
        now = datetime.now(timezone.utc)
        username_lower = username.lower()

        with self._lock:
            current = self._attempts.get(username_lower)

            if current is None:
                # First attempt
                info = LoginAttemptInfo(
                    count=1,
                    last_attempt=now,
                    locked_until=None,
                )
            elif current.locked_until is not None:
                # Already locked
                if now < current.locked_until:
                    # Still locked
                    info = current
                else:
                    # Lock expired, reset
                    info = LoginAttemptInfo(
                        count=1,
                        last_attempt=now,
                        locked_until=None,
                    )
            else:
                # Not locked, increment count
                new_count = current.count + 1
                locked_until = None

                if new_count >= max_attempts:
                    # Lock the account
                    locked_until = now + timedelta(minutes=lockout_minutes)

                info = LoginAttemptInfo(
                    count=new_count,
                    last_attempt=now,
                    locked_until=locked_until,
                )

            self._attempts[username_lower] = info
            return info

    def is_locked(self, username: str) -> bool:
        """Check if an account is currently locked."""
        username_lower = username.lower()
        now = datetime.now(timezone.utc)

        with self._lock:
            current = self._attempts.get(username_lower)
            if current is None:
                return False

            if current.locked_until is None:
                return False

            if now >= current.locked_until:
                # Lock expired, clear it
                self._attempts[username_lower] = LoginAttemptInfo(
                    count=current.count,
                    last_attempt=current.last_attempt,
                    locked_until=None,
                )
                return False

            return True

    def get_lock_remaining(self, username: str) -> int | None:
        """
        Get remaining lock time in minutes.

        Returns:
            Minutes remaining, or None if not locked
        """
        username_lower = username.lower()
        now = datetime.now(timezone.utc)

        with self._lock:
            current = self._attempts.get(username_lower)
            if current is None or current.locked_until is None:
                return None

            if now >= current.locked_until:
                return None

            remaining = current.locked_until - now
            return max(1, int(remaining.total_seconds() / 60))

    def clear_attempts(self, username: str) -> None:
        """Clear login attempts after successful login."""
        username_lower = username.lower()
        with self._lock:
            if username_lower in self._attempts:
                del self._attempts[username_lower]

    def reset_all(self) -> None:
        """Reset all login attempts (for testing)."""
        with self._lock:
            self._attempts.clear()


# Global instance
login_attempt_store = LoginAttemptStore()
