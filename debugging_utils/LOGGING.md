# Logging Configuration

## Overview

The PlayAble system logs all activity to both:
- **Console/Terminal**: Real-time output for monitoring
- **`run.log` file**: Persistent log file that aggregates all runs

## Log File: `run.log`

- **Location**: `run.log` in the project root directory
- **Mode**: Append mode - all runs are aggregated in one file
- **Format**: `YYYY-MM-DD HH:MM:SS - module_name - LEVEL - message`
- **Content**: All INFO, WARNING, and ERROR level messages from all components

## Features

- **Session Markers**: Each new run starts with a session marker:
  ```
  ================================================================================
  NEW SESSION STARTED - 2025-12-30 22:00:00
  ================================================================================
  ```

- **Aggregated Logs**: All runs are appended to the same file, so you can see the complete history

- **Dual Output**: Logs go to both console (for real-time monitoring) and file (for persistence)

## Log Levels

- **INFO**: Normal operation messages
- **WARNING**: Performance issues, non-critical problems
- **ERROR**: Critical errors that need attention

## Viewing Logs

### View entire log file:
```bash
cat run.log
```

### View last 100 lines:
```bash
tail -100 run.log
```

### Follow logs in real-time:
```bash
tail -f run.log
```

### Search for specific events:
```bash
grep "Gesture detected" run.log
grep "ERROR" run.log
grep "Session Started" run.log
```

### View logs from specific date:
```bash
grep "2025-12-30" run.log
```

## Log File Management

- **Size**: The log file will grow over time. Consider rotating it periodically
- **Backup**: You can backup `run.log` before clearing it
- **Clear**: To start fresh: `> run.log` or `rm run.log` (new file will be created on next run)
- **Git**: `run.log` is ignored by git (via `*.log` in `.gitignore`)

## Log Rotation (Optional)

For long-running systems, you may want to implement log rotation:

```bash
# Manual rotation
mv run.log run.log.old
# New run.log will be created automatically
```

Or use Python's `RotatingFileHandler` for automatic rotation (currently using simple `FileHandler`).

## Components Logging

All components log to the same file:
- Main orchestrator (`__main__`)
- Vision Sensor (`core.vision_sensor`)
- Gesture Detector (`core.gestures`)
- Web Server (`web.server`)
- PSN Connection Manager (`web.server`)
- Hardware Producer (via subprocess stdout/stderr)

## Troubleshooting

If `run.log` is not being created:
1. Check file permissions in the project directory
2. Verify the directory is writable
3. Check that logging is initialized before other modules

If logs are missing:
- Check that `setup_logging()` is called in `main.py` before importing other modules
- Verify no other code is calling `logging.basicConfig()` after setup

