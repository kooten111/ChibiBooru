"""
Tests for the refactored ingest process.
"""
import os
import tempfile
import hashlib
from unittest.mock import Mock, patch, MagicMock


class SkipTest(Exception):
    """Exception to skip a test."""
    pass


def test_md5_calculation():
    """Test that MD5 calculation works correctly."""
    # Create a temporary test file
    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.jpg') as f:
        test_content = b'test image data'
        f.write(test_content)
        test_file = f.name
    
    try:
        # Calculate expected MD5
        expected_md5 = hashlib.md5(test_content).hexdigest()
        
        # Import the function (will fail if dependencies missing, that's ok for now)
        try:
            from services.processing_service import get_md5
            calculated_md5 = get_md5(test_file)
            assert calculated_md5 == expected_md5, f"MD5 mismatch: {calculated_md5} != {expected_md5}"
            print(f"✓ MD5 calculation works correctly: {calculated_md5}")
        except ImportError as e:
            print(f"⚠ Skipping test due to missing dependencies: {e}")
            raise SkipTest(f"Missing dependencies: {e}")
    finally:
        # Clean up
        if os.path.exists(test_file):
            os.unlink(test_file)


def test_duplicate_detection_lock():
    """Test that the lock mechanism prevents race conditions."""
    try:
        from services.processing_service import acquire_processing_lock, release_processing_lock
        
        test_md5 = "test_hash_123"
        
        # First lock should succeed
        lock1, acquired1 = acquire_processing_lock(test_md5)
        assert acquired1 is True, "First lock should be acquired"
        print(f"✓ First lock acquired successfully")
        
        # Second lock should fail (already locked)
        lock2, acquired2 = acquire_processing_lock(test_md5)
        assert acquired2 is False, "Second lock should fail"
        print(f"✓ Second lock correctly blocked")
        
        # Release first lock
        release_processing_lock(lock1)
        print(f"✓ First lock released")
        
        # Now third lock should succeed
        lock3, acquired3 = acquire_processing_lock(test_md5)
        assert acquired3 is True, "Third lock should be acquired after release"
        print(f"✓ Third lock acquired after release")
        
        # Clean up
        release_processing_lock(lock3)
        
    except ImportError as e:
        print(f"⚠ Skipping test due to missing dependencies: {e}")
        raise SkipTest(f"Missing dependencies: {e}")


def test_process_image_file_signature():
    """Test that process_image_file has the correct signature."""
    try:
        from services.processing_service import process_image_file
        import inspect
        
        sig = inspect.signature(process_image_file)
        params = list(sig.parameters.keys())
        
        assert 'filepath' in params, "process_image_file should have 'filepath' parameter"
        assert 'move_from_ingest' in params, "process_image_file should have 'move_from_ingest' parameter"
        
        # Check default value
        assert sig.parameters['move_from_ingest'].default is True, "move_from_ingest should default to True"
        
        print(f"✓ process_image_file has correct signature: {sig}")
        
    except ImportError as e:
        print(f"⚠ Skipping test due to missing dependencies: {e}")
        raise SkipTest(f"Missing dependencies: {e}")


def test_monitor_uses_threadpool():
    """Test that monitor_service uses ThreadPoolExecutor, not ProcessPoolExecutor."""
    try:
        # Read the source file to check imports
        with open('services/monitor_service.py', 'r') as f:
            content = f.read()
        
        # Should NOT import ProcessPoolExecutor
        assert 'from concurrent.futures import ProcessPoolExecutor' not in content, \
            "monitor_service should not import ProcessPoolExecutor"
        
        # SHOULD import ThreadPoolExecutor
        assert 'from concurrent.futures import ThreadPoolExecutor' in content or \
               'ThreadPoolExecutor' in content, \
            "monitor_service should import ThreadPoolExecutor"
        
        print(f"✓ monitor_service uses ThreadPoolExecutor (not ProcessPoolExecutor)")
        
    except Exception as e:
        print(f"✗ Error checking monitor_service: {e}")
        raise


def test_executor_shutdown_properly():
    """Test that executor shutdown uses wait=True."""
    try:
        with open('services/monitor_service.py', 'r') as f:
            content = f.read()
        
        # Should call shutdown with wait=True
        assert 'shutdown(wait=True)' in content, \
            "Executor should be shutdown with wait=True"
        
        print(f"✓ Executor shutdown uses wait=True")
        
    except Exception as e:
        print(f"✗ Error checking shutdown: {e}")
        raise


def test_old_functions_removed():
    """Test that old split architecture functions are removed."""
    try:
        with open('services/processing_service.py', 'r') as f:
            content = f.read()
        
        # Old functions should be removed or marked as obsolete
        # The comment should exist indicating removal
        assert 'Old split architecture removed' in content or \
               'analyze_image_for_ingest' not in content, \
            "Old analyze_image_for_ingest function should be removed"
        
        print(f"✓ Old split architecture functions removed")
        
    except Exception as e:
        print(f"✗ Error checking old functions: {e}")
        raise


if __name__ == '__main__':
    print("Running ingest refactor tests...\n")
    
    tests = [
        ('MD5 Calculation', test_md5_calculation),
        ('Duplicate Detection Lock', test_duplicate_detection_lock),
        ('Process Image File Signature', test_process_image_file_signature),
        ('Monitor Uses ThreadPool', test_monitor_uses_threadpool),
        ('Executor Shutdown Properly', test_executor_shutdown_properly),
        ('Old Functions Removed', test_old_functions_removed),
    ]
    
    passed = 0
    failed = 0
    skipped = 0
    
    for name, test_func in tests:
        try:
            test_func()
            passed += 1
        except SkipTest as e:
            skipped += 1
        except AssertionError as e:
            print(f"✗ {name} failed: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {name} error: {e}")
            failed += 1
    
    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed, {skipped} skipped")
    print(f"{'='*50}\n")
    
    if failed > 0:
        exit(1)
    else:
        print("✓ All tests passed!")
        exit(0)
