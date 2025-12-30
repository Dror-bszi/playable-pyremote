# Gesture Detection Not Working - Fix Summary

## Problem

Gestures were not being detected and written to the pipe, even though the system was running.

## Issues Found

1. **Very Low FPS (2.3 FPS instead of 30+)**:
   - MediaPipe was taking ~360ms per frame (target: 33ms)
   - This severely limits gesture detection responsiveness

2. **No Diagnostic Logging**:
   - Couldn't see if poses were being detected
   - Couldn't see if gestures were being evaluated
   - Couldn't see if button events were being written

3. **MediaPipe Model Complexity Too High**:
   - Was set to `model_complexity=1` (balanced)
   - Too slow for Raspberry Pi hardware

## Fixes Applied

### 1. Reduced MediaPipe Model Complexity
**File: `core/gestures.py`**
- Changed `model_complexity` from `1` to `0` (fastest)
- This should significantly improve FPS on Raspberry Pi
- Trade-off: Slightly less accurate pose detection, but much faster

### 2. Added Diagnostic Logging
**Files: `core/gestures.py`, `core/vision_sensor.py`**
- Log when gestures are detected
- Log when poses are detected/not detected
- Log active mappings and thresholds on startup
- Periodic debug logs for gesture evaluation

### 3. Improved Error Visibility
- Better logging of gesture detection activity
- Periodic warnings if no pose detected

## Current Configuration

From `config/mappings.json`:
- **Active Mapping**: `left_elbow_raise` → `CROSS`
- **Thresholds**:
  - `delta_threshold`: 0.05 (speed of movement)
  - `raise_minimum`: 0.1 (range of movement)

## How to Test

1. **Restart the application**:
   ```bash
   python main.py --camera 0
   ```

2. **Check the logs** for:
   - "Active gesture mappings: {'left_elbow_raise': 'CROSS'}"
   - "Detection thresholds: {...}"
   - "Pose detected!" messages
   - "Gestures detected: ..." when you perform movements

3. **Try the gesture**:
   - Stand in front of the camera
   - Raise your left elbow above your left shoulder
   - You should see logs like: "Gestures detected: [('CROSS', 'press')]"
   - You should see: "Gesture activated: CROSS"

4. **Check FPS improvement**:
   - Look for "FPS: X.X" in logs
   - Should be higher than 2.3 FPS (ideally 10-15+ FPS with model_complexity=0)

## Troubleshooting

### Issue: Still no gesture detection

**Check 1: Is pose being detected?**
- Look for "Pose detected!" in logs
- If you see "No pose detected in frame" repeatedly:
  - Make sure you're fully visible to the camera
  - Check lighting conditions
  - Stand 3-6 feet from camera
  - Make sure camera can see your full upper body

**Check 2: Are mappings active?**
- Look for "Active gesture mappings: ..." in startup logs
- If empty, configure mappings via web dashboard or edit `config/mappings.json`

**Check 3: Are thresholds too strict?**
- Current thresholds might be too high for your movements
- Try lowering them via web dashboard:
  - `delta_threshold`: Try 0.02 (more sensitive to movement speed)
  - `raise_minimum`: Try 0.05 (smaller movements trigger detection)

**Check 4: Is the gesture correct?**
- For `left_elbow_raise`:
  - Raise your LEFT elbow above your LEFT shoulder
  - Movement should be relatively quick (not slow)
  - Elbow should be noticeably higher than shoulder

**Check 5: Is pipe connected?**
- Look for "Named Pipe opened successfully" in logs
- If you see "Failed to connect to pipe reader", the pipe reader might not be running

### Issue: FPS still very low

**Solutions**:
1. Close other applications
2. Reduce camera resolution (currently 640x480)
3. Check CPU usage: `top` or `htop`
4. Consider using a more powerful Raspberry Pi (Pi 4 or better)

### Issue: Gestures detected but not written to pipe

**Check**:
- Look for "Wrote event: CROSS press" in logs
- If you see "Pipe not open, cannot write event":
  - The pipe reader might not be connected
  - Check if pyremoteplay or other pipe reader is running

## Performance Expectations

With `model_complexity=0` on Raspberry Pi 3B:
- **Expected FPS**: 10-15 FPS (much better than 2.3 FPS)
- **Frame processing time**: ~70-100ms (better than 360ms)
- **Gesture detection**: Should be responsive enough for rehabilitation use

For better performance:
- Use Raspberry Pi 4 or better
- Consider using GPU acceleration if available
- Reduce camera resolution if needed

## Next Steps

1. **Restart the application** and test gesture detection
2. **Monitor logs** to see:
   - If poses are detected
   - If gestures are evaluated
   - If button events are written
3. **Adjust thresholds** if gestures are too sensitive or not sensitive enough
4. **Add more mappings** via web dashboard if needed

## Additional Notes

- The low FPS was the main bottleneck - MediaPipe processing was taking too long
- With `model_complexity=0`, detection should be much more responsive
- Gesture detection requires:
  1. Pose detection (MediaPipe finds your body)
  2. Gesture evaluation (checks if movement matches gesture)
  3. Threshold comparison (movement must meet speed/range requirements)
  4. State change detection (only sends press on new activation)
  5. Pipe write (sends button event to pipe)

All of these steps must work for gestures to be detected and sent to the pipe.

