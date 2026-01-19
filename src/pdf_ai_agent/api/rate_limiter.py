"""
Simple in-memory rate limiter for authentication endpoints.
"""
from datetime import datetime, timedelta
from typing import Dict, Tuple
from collections import defaultdict
import threading


class RateLimiter:
    """
    Simple in-memory rate limiter with sliding window.
    
    This implementation tracks failed login attempts by IP and email
    to prevent brute force attacks.
    """
    
    def __init__(self, max_attempts: int = 5, window_seconds: int = 600):
        """
        Initialize rate limiter.
        
        Args:
            max_attempts: Maximum number of failed attempts allowed
            window_seconds: Time window in seconds (default: 600 = 10 minutes)
        """
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: Dict[str, list] = defaultdict(list)
        self._lock = threading.Lock()
    
    def _clean_old_attempts(self, key: str, now: datetime):
        """Remove attempts older than the window."""
        cutoff = now - timedelta(seconds=self.window_seconds)
        self._attempts[key] = [
            attempt_time for attempt_time in self._attempts[key]
            if attempt_time > cutoff
        ]
    
    def is_rate_limited(self, key: str) -> Tuple[bool, int]:
        """
        Check if a key is rate limited.
        
        Args:
            key: Identifier to check (e.g., IP address or email)
            
        Returns:
            Tuple of (is_limited, retry_after_seconds)
        """
        with self._lock:
            now = datetime.utcnow()
            self._clean_old_attempts(key, now)
            
            attempts = self._attempts[key]
            if len(attempts) >= self.max_attempts:
                # Calculate retry after time
                oldest_attempt = min(attempts)
                retry_after = int((oldest_attempt + timedelta(seconds=self.window_seconds) - now).total_seconds())
                return True, max(0, retry_after)
            
            return False, 0
    
    def record_failed_attempt(self, key: str):
        """
        Record a failed login attempt.
        
        Args:
            key: Identifier to record (e.g., IP address or email)
        """
        with self._lock:
            now = datetime.utcnow()
            self._clean_old_attempts(key, now)
            self._attempts[key].append(now)
    
    def clear_attempts(self, key: str):
        """
        Clear all attempts for a key (e.g., after successful login).
        
        Args:
            key: Identifier to clear
        """
        with self._lock:
            if key in self._attempts:
                del self._attempts[key]


# Global rate limiter instance
rate_limiter = RateLimiter(max_attempts=5, window_seconds=600)
