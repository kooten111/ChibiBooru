import unittest
import sys
import os

# Add parent directory to path to import services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.processing_service import AdaptiveSauceNAORateLimiter

class TestRateLimiter(unittest.TestCase):
    def test_rate_limiter_logic(self):
        limiter = AdaptiveSauceNAORateLimiter()
        
        # 1. Initial state
        self.assertIsNone(limiter.current_limit)
        
        # 2. Simulate hitting a rate limit to enter 'guessing' mode
        limiter.record_rate_limit_hit()
        # It should drop to a safe low limit (e.g. 1)
        self.assertEqual(limiter.current_limit, 1)
        
        # 3. Simulate a successful request with explicit limit
        explicit_limit = 17
        limiter.record_success(actual_limit=explicit_limit)
        
        self.assertEqual(limiter.current_limit, explicit_limit)
            
        # 4. Hybrid test: What if we don't pass a limit (legacy behavior)?
        # It should stay at the current limit
        limiter.record_success(actual_limit=None)
        self.assertEqual(limiter.current_limit, explicit_limit)

if __name__ == '__main__':
    unittest.main()
