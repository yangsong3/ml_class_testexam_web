from threading import Lock
from time import monotonic


class LoginAttemptTracker:
    """접속 주소별 로그인 실패 횟수와 차단 시간을 관리한다."""

    def __init__(self, max_attempts: int = 5, window_seconds: int = 300) -> None:
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._failures: dict[str, list[float]] = {}
        self._lock = Lock()

    def is_blocked(self, address: str) -> bool:
        """최근 실패 횟수가 제한을 넘었는지 반환한다."""
        with self._lock:
            failures = self._recent_failures(address)
            return len(failures) >= self._max_attempts

    def record_failure(self, address: str) -> None:
        """로그인 실패 시각을 기록한다."""
        with self._lock:
            failures = self._recent_failures(address)
            failures.append(monotonic())
            self._failures[address] = failures

    def clear(self, address: str) -> None:
        """로그인 성공 주소의 실패 기록을 제거한다."""
        with self._lock:
            self._failures.pop(address, None)

    def _recent_failures(self, address: str) -> list[float]:
        threshold = monotonic() - self._window_seconds
        failures = [
            failure
            for failure in self._failures.get(address, [])
            if failure >= threshold
        ]
        if failures:
            self._failures[address] = failures
        else:
            self._failures.pop(address, None)
        return failures
