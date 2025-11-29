
import unittest
import time
import threading
from unittest.mock import MagicMock, patch
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock modules before importing monitor_service
sys.modules['database_models'] = MagicMock()
sys.modules['services.processing_service'] = MagicMock()
sys.modules['config'] = MagicMock()
sys.modules['utils.file_utils'] = MagicMock()
sys.modules['watchdog.observers'] = MagicMock()

# Create a dummy class for FileSystemEventHandler so inheritance works
class DummyHandler:
    def __init__(self):
        pass

# Mock the module with our dummy class
events_mock = MagicMock()
events_mock.FileSystemEventHandler = DummyHandler
sys.modules['watchdog.events'] = events_mock

# Now import the service to test
from services import monitor_service

class TestMonitorBatching(unittest.TestCase):
    def setUp(self):
        # Configure config mock
        sys.modules['config'].INGEST_DIRECTORY = "/tmp/ingest"
        
        # Reset monitor status
        monitor_service.monitor_status["pending_reload"] = False
        monitor_service.monitor_status["last_activity"] = 0
        monitor_service.monitor_status["running"] = True
        monitor_service.monitor_status["logs"] = []
        
        # Mock dependencies
        self.mock_processing = sys.modules['services.processing_service']
        self.mock_processing.process_image_file.return_value = True
        
        self.mock_models = sys.modules['database_models']
        self.mock_models.get_all_filepaths.return_value = []
        
        # Create handler
        self.handler = monitor_service.ImageFileHandler(watch_ingest=True)

    def test_batching_logic(self):
        print("\nTesting batching logic...")
        
        # Simulate 5 rapid file events
        for i in range(5):
            event = MagicMock()
            event.is_directory = False
            # Use a path that starts with the ingest directory
            event.src_path = f"/tmp/ingest/test_image_{i}.jpg"
            
            # Mock os.path.abspath to return the path as-is (simplification)
            with patch('os.path.abspath', side_effect=lambda p: str(p)):
                 with patch('os.path.exists', return_value=True):
                    self.handler.on_created(event)
            
            print(f"Processed file {i}")
        
        # Verify pending_reload is True
        self.assertTrue(monitor_service.monitor_status["pending_reload"], "pending_reload should be True")
        print("pending_reload is correctly set to True")
        
        # Verify last_activity is recent
        self.assertAlmostEqual(monitor_service.monitor_status["last_activity"], time.time(), delta=1.0)
        
        # Verify load_data_from_db has NOT been called yet (it's handled by the loop, not the handler)
        self.mock_models.load_data_from_db.assert_not_called()
        print("load_data_from_db was NOT called immediately (Correct)")

    def test_debounce_loop(self):
        print("\nTesting debounce loop logic...")
        
        # Set up state as if files were just processed
        monitor_service.monitor_status["pending_reload"] = True
        monitor_service.monitor_status["last_activity"] = time.time()
        
        # 1. Check immediately - should NOT reload yet
        if monitor_service.monitor_status["pending_reload"]:
            if time.time() - monitor_service.monitor_status["last_activity"] > 2.0:
                self.mock_models.load_data_from_db()
                monitor_service.monitor_status["pending_reload"] = False
        
        self.mock_models.load_data_from_db.assert_not_called()
        print("Debounce check 1: No reload yet (Correct)")
        
        # 2. Simulate waiting 2.1 seconds
        print("Simulating 2.1s wait...")
        monitor_service.monitor_status["last_activity"] -= 2.1
        
        # Check again
        if monitor_service.monitor_status["pending_reload"]:
            if time.time() - monitor_service.monitor_status["last_activity"] > 2.0:
                self.mock_models.load_data_from_db()
                monitor_service.monitor_status["pending_reload"] = False
                
        self.mock_models.load_data_from_db.assert_called_once()
        self.assertFalse(monitor_service.monitor_status["pending_reload"])
        print("Debounce check 2: Reloaded successfully (Correct)")

if __name__ == '__main__':
    unittest.main()
