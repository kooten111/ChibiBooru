
import unittest
import asyncio
import time
from unittest.mock import MagicMock, patch
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock modules
sys.modules['database_models'] = MagicMock()
sys.modules['services.processing_service'] = MagicMock()
sys.modules['config'] = MagicMock()
sys.modules['utils.file_utils'] = MagicMock()
sys.modules['watchdog.observers'] = MagicMock()
sys.modules['watchdog.events'] = MagicMock()
sys.modules['services.switch_source_db'] = MagicMock()
sys.modules['services.api_service'] = MagicMock()
sys.modules['services.monitor_service'] = MagicMock()
sys.modules['services.implication_service'] = MagicMock()
sys.modules['services.rating_service'] = MagicMock()

# Mock system_service to simulate a slow scan
mock_system_service = MagicMock()
def slow_scan():
    time.sleep(1) # Block for 1 second
    return {"status": "success"}
mock_system_service.scan_and_process_service = slow_scan
sys.modules['services.system_service'] = mock_system_service

from routers.api.system import trigger_scan

class TestAsyncScan(unittest.TestCase):
    def test_scan_is_async(self):
        print("\nTesting async scan endpoint...")
        
        async def run_test():
            start_time = time.time()
            
            # Start the scan task
            scan_task = asyncio.create_task(trigger_scan())
            
            # Immediately try to do something else on the event loop
            # If trigger_scan blocks, this won't run until scan finishes (1s)
            # If trigger_scan is async, this runs immediately
            await asyncio.sleep(0.1)
            mid_time = time.time()
            
            # Wait for scan to finish
            await scan_task
            end_time = time.time()
            
            print(f"Time to first await: {mid_time - start_time:.4f}s")
            print(f"Total time: {end_time - start_time:.4f}s")
            
            # The "something else" should have happened quickly (< 0.5s)
            # If it took > 1s, then the scan blocked the loop
            self.assertLess(mid_time - start_time, 0.5, "Event loop was blocked!")
            
        asyncio.run(run_test())

if __name__ == '__main__':
    unittest.main()
