# Monitor Service Architecture - Standalone Process

## Overview

As of this update, ChibiBooru uses a **two-process architecture** for production deployment:

1. **Web Workers (uvicorn)**: Handle HTTP requests with multiple workers for scalability
2. **Monitor Service (standalone)**: Single background process that watches for new files

This architecture ensures only **one monitor** runs regardless of how many web workers are active, preventing:
- Duplicate file processing
- Race conditions from multiple monitors
- Wasted system resources
- Confusing logs with multiple "Monitor started" messages

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                   start_booru.sh                        │
│                  (Process Manager)                      │
└────────────────────┬────────────────────────────────────┘
                     │
           ┌─────────┴─────────┐
           │                   │
           ▼                   ▼
┌──────────────────┐  ┌──────────────────────┐
│  monitor_runner  │  │  uvicorn (main)      │
│   (PID: 1234)    │  │   (PID: 1235)        │
│                  │  │                      │
│ - Watch folders  │  │  ├─ Worker 1         │
│ - Process files  │  │  ├─ Worker 2         │
│ - Auto-shutdown  │  │  ├─ Worker 3         │
│                  │  │  └─ Worker 4         │
└──────────────────┘  └──────────────────────┘
         ▲                     │
         │   Periodic Check    │
         └─────────────────────┘
      (Shuts down if main dies)
```

## Key Components

### 1. monitor_runner.py (NEW)

A standalone script that:
- Initializes the database
- Loads data from DB
- Starts the monitor service
- Runs indefinitely until interrupted
- Handles graceful shutdown on SIGINT/SIGTERM
- Exits automatically if the main app stops (process coordination)

**Location:** `/monitor_runner.py`

**Usage:**
```bash
python monitor_runner.py
```

### 2. app.py (MODIFIED)

The monitor startup code has been **removed** from `create_app()`:

**Before:**
```python
if config.MONITOR_ENABLED:
    from services import monitor_service
    if monitor_service.start_monitor():
        logger.info("✓ Monitor service started automatically")
```

**After:**
```python
# Note: Monitor service is now run as a standalone process (monitor_runner.py)
# and is started by start_booru.sh. This prevents duplicate monitors when
# using multiple uvicorn workers.
```

### 3. start_booru.sh (UPDATED)

The startup script now:
- Starts `monitor_runner.py` in the background
- Captures its PID
- Sets up a trap to kill the monitor when the script exits
- Starts uvicorn in the foreground (as before)
- Kills the monitor when uvicorn exits (via trap)

**Key Features:**
```bash
# Start monitor in background
python monitor_runner.py &
MONITOR_PID=$!

# Trap ensures monitor is killed when script exits
trap "kill $MONITOR_PID 2>/dev/null; exit" INT TERM EXIT

# Start web server (foreground)
uvicorn app:create_app --factory --host $HOST --port $PORT --workers $WORKERS
```

## Process Coordination

### How the Monitor Knows to Shutdown

The monitor uses **process detection** to automatically shut down when the main app dies:

1. Every 10 seconds, the monitor checks if uvicorn is running
2. It searches for processes with `uvicorn` in the command line
3. If no uvicorn process is found, the monitor initiates graceful shutdown
4. This prevents orphaned monitor processes

**Implementation:**
```python
def is_main_app_running():
    """Check if the main uvicorn application is still running."""
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        cmdline = proc.info.get('cmdline', [])
        if cmdline and any('uvicorn' in arg for arg in cmdline):
            if any('app:' in arg for arg in cmdline):
                return True
    return False
```

## Deployment

### Starting the Application

**Production Mode (Recommended):**
```bash
./start_booru.sh
```

This starts:
- Monitor service in background (1 process)
- Web server with 4 workers (5 processes: 1 main + 4 workers)

**Development Mode:**
```bash
python app.py
```

This starts:
- Web server with 1 worker (no monitor)

### Stopping the Application

**Normal Shutdown:**
```bash
# Press Ctrl+C in the terminal where start_booru.sh is running
# Both monitor and web server will stop gracefully
```

**Force Stop:**
```bash
# Find the processes
ps aux | grep -E "uvicorn|monitor_runner"

# Kill the main process (this triggers the trap, which kills the monitor)
kill <uvicorn_main_pid>

# Or kill both individually
kill <monitor_pid>
kill <uvicorn_pid>
```

### Verifying Deployment

After starting, verify the architecture:

1. **Check Processes:**
   ```bash
   ps aux | grep python
   # Should see:
   # - 1 monitor_runner.py process
   # - 5 uvicorn processes (1 main + 4 workers)
   ```

2. **Check Logs:**
   ```bash
   tail -f logs/app.log
   # Should see only ONE "Monitor service started" message
   ```

3. **Test Shutdown:**
   ```bash
   # Press Ctrl+C
   # Should see:
   # - "Stopping monitor..."
   # - "✓ Monitor stopped"
   # Both processes should exit cleanly
   ```

4. **Test Auto-Shutdown:**
   ```bash
   # Find and kill just the uvicorn main process
   ps aux | grep uvicorn | grep -v worker
   kill <uvicorn_main_pid>
   
   # Wait 10-15 seconds
   # Monitor should detect this and shut down automatically
   ps aux | grep monitor_runner  # Should show nothing
   ```

## Configuration

### Environment Variables

**UVICORN_WORKERS** (default: 4)
- Number of web workers to spawn
- Set as environment variable or in `start_booru.sh`
- Can be overridden at runtime: `UVICORN_WORKERS=8 ./start_booru.sh`

**MONITOR_ENABLED** (default: True)
- Controls whether monitor service starts
- Loaded via config priority chain: `config.yml` → `.env` → Python default in `config.py`
- Can be edited via web UI at `/system`

### Customizing Worker Count

Edit `.env`:
```env
UVICORN_WORKERS=8  # For more concurrent request handling
```

Or set at runtime:
```bash
UVICORN_WORKERS=2 ./start_booru.sh
```

## Troubleshooting

### Monitor Not Starting

**Symptom:** Only web server starts, no monitor process

**Cause:** MONITOR_ENABLED is False

**Solution:**
```bash
# Check config
grep MONITOR_ENABLED config.py

# Enable monitoring
# In config.py, ensure:
MONITOR_ENABLED = True
```

### Multiple Monitors Running

**Symptom:** Multiple "Monitor service started" messages in logs

**Cause:** Old code still in `app.py` or manual monitor start

**Solution:**
```bash
# Check app.py doesn't start monitor
grep "monitor_service.start_monitor" app.py
# Should find no matches or only commented lines

# Kill all monitors
pkill -f monitor_runner.py

# Restart with start_booru.sh
./start_booru.sh
```

### Monitor Doesn't Stop with Main App

**Symptom:** Monitor keeps running after killing uvicorn

**Cause:** Process coordination not working (requires psutil)

**Solution:**
```bash
# Install psutil (from project root with venv activated)
uv pip install psutil   # or: pip install psutil

# Verify psutil is installed
python -c "import psutil; print(psutil.__version__)"

# Restart the application
./start_booru.sh
```

### Orphaned Monitor Process

**Symptom:** Monitor running but no web server

**Cause:** Manual monitor start or crash

**Solution:**
```bash
# Find the monitor
ps aux | grep monitor_runner

# Kill it
kill <monitor_pid>

# Restart properly
./start_booru.sh
```

## Migration from Old Architecture

If upgrading from a version where monitors ran per-worker:

1. **Stop the application:**
   ```bash
   # Stop all uvicorn workers
   pkill -f uvicorn
   
   # Stop any running monitors
   pkill -f monitor_runner
   ```

2. **Pull the new code:**
   ```bash
   git pull origin <branch>
   ```

3. **Install dependencies:**
   ```bash
   uv pip install psutil   # or: pip install -r requirements.txt
   ```

4. **Start with new script:**
   ```bash
   ./start_booru.sh
   ```

5. **Verify:**
   ```bash
   # Should see only 1 monitor
   ps aux | grep monitor_runner | wc -l  # Should output: 1
   
   # Should see multiple workers
   ps aux | grep uvicorn | wc -l  # Should output: 5 (1 main + 4 workers)
   ```

## Benefits

### Before (Per-Worker Monitors)

With `--workers 4`:
- 4 separate monitors watching the same directories
- 4 separate ThreadPoolExecutors (16+ threads total)
- Massive duplication of work
- Race conditions when multiple monitors process the same file
- Logs showing "✓ Monitor service started" 4 times

### After (Standalone Monitor)

With `--workers 4`:
- 1 monitor watching directories
- 1 ThreadPoolExecutor (4 threads by default)
- No duplicate work
- No race conditions
- Logs showing "✓ Monitor service started" 1 time
- Web workers can scale independently

### Performance Impact

**Memory:**
- Before: ~200MB per monitor × 4 = ~800MB wasted
- After: ~200MB total for 1 monitor
- **Savings:** ~600MB

**CPU:**
- Before: 4 watchdog observers, 4 executors, duplicate file processing
- After: 1 watchdog observer, 1 executor, single file processing
- **Savings:** ~75% reduction in monitoring overhead

**Disk I/O:**
- Before: 4 simultaneous scanners, potential conflicts
- After: 1 scanner, sequential processing
- **Improvement:** Cleaner I/O patterns, no conflicts

## Future Enhancements

Potential improvements to the architecture:

1. **Health Monitoring:** Add `/health` endpoint to monitor_runner for systemd watchdog
2. **Graceful Reload:** Support SIGHUP for config reload without restart
3. **Metrics Export:** Export monitoring metrics (files processed, errors, etc.)
4. **Multi-Server Coordination:** Use database locks for multi-server deployments
5. **Dynamic Thread Scaling:** Adjust executor threads based on load

## Reference

**Related Files:**
- `monitor_runner.py` - Standalone monitor script
- `app.py` - Web application (monitor code removed)
- `start_booru.sh` - Startup script with process coordination
- `services/monitor_service.py` - Monitor service implementation (unchanged)

**Related Documentation:**
- [README.md](../README.MD) - Updated usage instructions
- [SERVICES.md](SERVICES.md) - Monitor service documentation
- [INGEST_REFACTOR.md](INGEST_REFACTOR.md) - Previous ingest improvements

**Dependencies:**
- `psutil>=5.9.0` - Process monitoring and coordination
- `watchdog>=6.0.0` - File system monitoring
