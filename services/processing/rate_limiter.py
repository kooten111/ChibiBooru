"""
Adaptive rate limiter for SauceNAO API requests.
"""

import time
from collections import deque
from threading import Lock


class AdaptiveSauceNAORateLimiter:
    """
    Adaptive rate limiter for SauceNAO API requests.

    Automatically learns the rate limits by:
    - Starting with no limits (unlimited requests)
    - When hitting 429 error, backs off to conservative limit
    - Periodically tests if limits can be increased
    - Adjusts down immediately on 429, adjusts up gradually
    """

    def __init__(self):
        """Initialize the adaptive rate limiter."""
        # Current rate limit (None = unlimited)
        self.current_limit = None  # requests per 30 seconds
        self.window_duration = 30  # seconds

        # Track request timestamps in current window
        self.requests = deque()

        # Rate limit learning
        self.last_rate_limit_hit = None  # timestamp of last 429 error
        self.consecutive_successes = 0   # successful requests since last 429
        self.test_threshold = 50         # test limit increase every N successful requests

        # Backoff state
        self.in_backoff = False
        self.backoff_until = None

        # Thread safety
        self.lock = Lock()

    def _clean_old_requests(self):
        """Remove requests older than the window."""
        current_time = time.time()
        cutoff_time = current_time - self.window_duration

        while self.requests and self.requests[0] < cutoff_time:
            self.requests.popleft()

    def should_wait(self):
        """
        Check if we should wait before making a request.

        Returns:
            tuple: (should_wait: bool, wait_time: float)
        """
        with self.lock:
            current_time = time.time()

            # Check if we're in backoff period
            if self.in_backoff and self.backoff_until:
                if current_time < self.backoff_until:
                    return True, self.backoff_until - current_time
                else:
                    self.in_backoff = False
                    self.backoff_until = None

            # Clean old requests
            self._clean_old_requests()

            # If no limit set, don't wait
            if self.current_limit is None:
                return False, 0

            # Check if we're at the limit
            if len(self.requests) >= self.current_limit:
                oldest_request = self.requests[0]
                wait_time = (oldest_request + self.window_duration) - current_time
                return True, max(0, wait_time)

            return False, 0

    def wait_if_needed(self):
        """Block until a request can be made."""
        should_wait, wait_time = self.should_wait()

        if should_wait and wait_time > 0:
            with self.lock:
                limit_str = f"{self.current_limit}/{self.window_duration}s" if self.current_limit else "unlimited"
            print(f"[SauceNAO Adaptive] Waiting {wait_time:.1f}s (current limit: {limit_str})")
            time.sleep(wait_time)

    def record_success(self, actual_limit=None):
        """
        Record a successful request.
        
        Args:
            actual_limit (int, optional): The actual short_limit returned by the API.
        """
        with self.lock:
            current_time = time.time()
            self.requests.append(current_time)
            self.consecutive_successes += 1

            # specific update logic: if the API gave us an explicit limit, use it!
            if actual_limit is not None:
                # If we were guessing, or if the limit changed, update it
                if self.current_limit != actual_limit:
                    print(f"[SauceNAO Adaptive] Updating limit from API header: {self.current_limit} -> {actual_limit}")
                    self.current_limit = actual_limit
                    # We can trust this limit, so we don't need to be in "testing" mode
            
            # Fallback to adaptive probing ONLY if we don't have an explicit limit
            # (This shouldn't happen often if we're parsing headers correctly)
            elif (self.current_limit is not None and
                self.consecutive_successes >= self.test_threshold and
                self.last_rate_limit_hit and
                (current_time - self.last_rate_limit_hit) > 300):  # 5 minutes since last 429

                old_limit = self.current_limit
                self.current_limit += 1
                self.consecutive_successes = 0
                print(f"[SauceNAO Adaptive] Testing higher limit: {old_limit} -> {self.current_limit}")

    def record_rate_limit_hit(self):
        """Record that we hit a 429 rate limit error."""
        with self.lock:
            current_time = time.time()
            self.last_rate_limit_hit = current_time
            self.consecutive_successes = 0

            # Clean old requests to see how many we made in the window
            self._clean_old_requests()
            requests_in_window = len(self.requests)

            if self.current_limit is None:
                # First time hitting limit - set conservative limit
                new_limit = max(1, requests_in_window - 1)
                print(f"[SauceNAO Adaptive] Rate limit detected! Setting limit to {new_limit}/{self.window_duration}s")
                self.current_limit = new_limit
            else:
                # We hit the limit again - decrease
                old_limit = self.current_limit
                self.current_limit = max(1, self.current_limit - 1)
                print(f"[SauceNAO Adaptive] Rate limit hit again! Reducing: {old_limit} -> {self.current_limit}")

            # Enter backoff period
            self.in_backoff = True
            self.backoff_until = current_time + self.window_duration
            print(f"[SauceNAO Adaptive] Entering {self.window_duration}s cooldown period")

    def get_stats(self):
        """Get current rate limiter statistics."""
        with self.lock:
            self._clean_old_requests()

            return {
                "current_limit": self.current_limit,
                "requests_in_window": len(self.requests),
                "window_duration": self.window_duration,
                "consecutive_successes": self.consecutive_successes,
                "in_backoff": self.in_backoff,
                "last_limit_hit": self.last_rate_limit_hit
            }


# Global adaptive SauceNAO rate limiter instance
saucenao_rate_limiter = AdaptiveSauceNAORateLimiter()
