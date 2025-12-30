# Debugging Utilities

This folder contains debugging scripts and diagnostic documentation for troubleshooting the PlayAble system.

## Scripts

### `diagnose_camera.py`
Comprehensive camera diagnostic tool that checks:
- USB device detection
- Video device nodes (`/dev/video*`)
- User permissions
- Kernel modules
- OpenCV camera access
- Camera capabilities

**Usage:**
```bash
python3 debugging_utils/diagnose_camera.py
```

### `test_video_feed.py`
Test script to verify video feed functionality:
- Direct camera access
- GestureDetector initialization
- `get_current_frame()` functionality
- Frame processing

**Usage:**
```bash
python3 debugging_utils/test_video_feed.py
```

## Documentation

### `CAMERA_DIAGNOSTICS.md`
Summary of camera diagnostic findings and troubleshooting steps for USB camera detection issues.

### `VIDEO_FEED_FIX.md`
Documentation of the video feed fix, explaining why the web server wasn't showing camera frames and how it was resolved.

### `GESTURE_DETECTION_FIX.md`
Documentation of gesture detection issues, performance optimizations, and troubleshooting guide.

## When to Use

Use these tools when:
- Camera is not being detected
- Video feed is not working
- Gesture detection is not working
- Performance issues (low FPS)
- Need to verify system configuration

## Notes

- These are debugging utilities and not part of the main application
- They can be safely removed if not needed
- They require the same dependencies as the main application

