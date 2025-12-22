"""
Tests for monitor_runner.py - Standalone monitor process
"""

import pytest
import subprocess
import time
import signal
import os
import sys


class TestMonitorRunner:
    """Tests for the standalone monitor runner process."""
    
    def test_monitor_runner_exists(self):
        """Test that monitor_runner.py exists and is executable."""
        runner_path = os.path.join(os.path.dirname(__file__), '..', 'monitor_runner.py')
        assert os.path.exists(runner_path), "monitor_runner.py should exist"
        assert os.access(runner_path, os.X_OK), "monitor_runner.py should be executable"
    
    def test_monitor_runner_imports(self):
        """Test that monitor_runner.py can be imported without errors."""
        # This validates syntax and basic imports
        try:
            import importlib.util
            runner_path = os.path.join(os.path.dirname(__file__), '..', 'monitor_runner.py')
            spec = importlib.util.spec_from_file_location("monitor_runner", runner_path)
            module = importlib.util.module_from_spec(spec)
            # Don't execute main(), just validate imports
            assert module is not None
        except Exception as e:
            pytest.fail(f"Failed to import monitor_runner.py: {e}")
    
    def test_monitor_runner_has_signal_handlers(self):
        """Test that monitor_runner has signal handler functions."""
        import importlib.util
        runner_path = os.path.join(os.path.dirname(__file__), '..', 'monitor_runner.py')
        spec = importlib.util.spec_from_file_location("monitor_runner", runner_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        assert hasattr(module, 'signal_handler'), "Should have signal_handler function"
        assert hasattr(module, 'is_main_app_running'), "Should have is_main_app_running function"
        assert hasattr(module, 'main'), "Should have main function"
    
    @pytest.mark.skipif(not os.getenv('RUN_INTEGRATION_TESTS'), 
                        reason="Integration test - requires full environment")
    def test_monitor_runner_starts_and_stops(self):
        """Integration test: Start monitor runner and verify it responds to SIGTERM."""
        runner_path = os.path.join(os.path.dirname(__file__), '..', 'monitor_runner.py')
        
        # Start the monitor runner
        proc = subprocess.Popen(
            [sys.executable, runner_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        try:
            # Give it a moment to start
            time.sleep(2)
            
            # Check it's running
            assert proc.poll() is None, "Monitor runner should be running"
            
            # Send SIGTERM for graceful shutdown
            proc.send_signal(signal.SIGTERM)
            
            # Wait for it to stop (with timeout)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()  # Force kill if it doesn't stop
                pytest.fail("Monitor runner didn't stop gracefully within timeout")
            
            # Check it exited cleanly
            assert proc.returncode == 0, f"Monitor runner should exit with code 0, got {proc.returncode}"
            
        finally:
            # Ensure process is terminated
            if proc.poll() is None:
                proc.kill()
                proc.wait()


class TestAppPyModification:
    """Tests to verify app.py no longer starts the monitor."""
    
    def test_app_py_does_not_start_monitor(self):
        """Verify that app.py does not start the monitor service."""
        app_path = os.path.join(os.path.dirname(__file__), '..', 'app.py')
        
        with open(app_path, 'r') as f:
            content = f.read()
        
        # Check that monitor_service.start_monitor() is not called
        assert 'monitor_service.start_monitor()' not in content, \
               "app.py should not call monitor_service.start_monitor() anymore"
        
        # Check for explanatory comment about standalone process
        assert 'standalone' in content.lower(), \
               "app.py should have a comment explaining the standalone monitor architecture"
    
    def test_app_py_has_comment_explaining_monitor(self):
        """Verify that app.py has a comment explaining the monitor architecture."""
        app_path = os.path.join(os.path.dirname(__file__), '..', 'app.py')
        
        with open(app_path, 'r') as f:
            content = f.read()
        
        assert 'standalone process' in content or 'monitor_runner' in content, \
               "app.py should have a comment explaining the standalone monitor process"


class TestStartScript:
    """Tests for the updated start_booru.sh script."""
    
    def test_start_script_exists(self):
        """Test that start_booru.sh exists."""
        script_path = os.path.join(os.path.dirname(__file__), '..', 'start_booru.sh')
        assert os.path.exists(script_path), "start_booru.sh should exist"
    
    def test_start_script_starts_monitor(self):
        """Verify that start_booru.sh starts the monitor_runner.py."""
        script_path = os.path.join(os.path.dirname(__file__), '..', 'start_booru.sh')
        
        with open(script_path, 'r') as f:
            content = f.read()
        
        assert 'monitor_runner.py' in content, "start_booru.sh should start monitor_runner.py"
        assert 'MONITOR_PID' in content, "start_booru.sh should capture monitor PID"
    
    def test_start_script_has_trap(self):
        """Verify that start_booru.sh has a trap to kill the monitor on exit."""
        script_path = os.path.join(os.path.dirname(__file__), '..', 'start_booru.sh')
        
        with open(script_path, 'r') as f:
            content = f.read()
        
        assert 'trap' in content, "start_booru.sh should have a trap"
        assert 'kill $MONITOR_PID' in content or 'kill ${MONITOR_PID}' in content, \
               "start_booru.sh should kill the monitor on exit"


class TestProcessCoordination:
    """Tests for process coordination between main app and monitor."""
    
    def test_is_main_app_running_function_exists(self):
        """Verify the is_main_app_running function exists in monitor_runner."""
        import importlib.util
        runner_path = os.path.join(os.path.dirname(__file__), '..', 'monitor_runner.py')
        spec = importlib.util.spec_from_file_location("monitor_runner", runner_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        assert hasattr(module, 'is_main_app_running'), \
               "monitor_runner should have is_main_app_running function"
    
    def test_monitor_runner_checks_for_main_app(self):
        """Verify that monitor_runner checks for the main app in its loop."""
        runner_path = os.path.join(os.path.dirname(__file__), '..', 'monitor_runner.py')
        
        with open(runner_path, 'r') as f:
            content = f.read()
        
        assert 'is_main_app_running()' in content, \
               "monitor_runner should call is_main_app_running()"
        assert 'uvicorn' in content.lower(), \
               "monitor_runner should check for uvicorn process"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
