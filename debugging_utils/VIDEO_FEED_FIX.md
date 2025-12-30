# Video Feed Fix - Web Server Not Showing Camera

## Problem

The web server video feed was not displaying camera frames, showing blank or error frames instead.

## Root Cause

The `get_current_frame()` method in `core/gestures.py` was returning `None` if no frames had been processed yet by the VisionSensor loop. This happened because:

1. `get_current_frame()` only returned frames if `self.current_frame` was set
2. `self.current_frame` is only set when `process_frame()` is called
3. `process_frame()` is called by the VisionSensor in its processing loop
4. The web server might request frames before the VisionSensor has processed any frames
5. This created a race condition where the video feed showed blank frames

## Solution

I've updated `get_current_frame()` to:

1. **Read directly from camera if no frame processed yet**: If `current_frame` is `None`, the method now reads a fresh frame directly from the camera
2. **Process the frame for pose detection**: It processes the frame to get pose landmarks for visualization
3. **Always return a frame if camera is available**: The method now ensures a frame is returned whenever the camera is accessible

### Changes Made

**File: `core/gestures.py`**
- Modified `get_current_frame()` to read directly from camera when `current_frame` is `None`
- Added pose processing for frames read directly from camera
- Improved error handling

**File: `web/server.py`**
- Enhanced error messages in video feed route
- Added better logging for debugging
- Improved error frame display with helpful messages

## Testing

Run the test script to verify everything works:

```bash
python3 debugging_utils/test_video_feed.py
```

This will test:
1. Direct camera access
2. GestureDetector initialization
3. `get_current_frame()` functionality
4. Frame processing

## Verification Steps

1. **Start the application**:
   ```bash
   python main.py --camera 0
   ```

2. **Check logs** for:
   - "Camera initialized successfully"
   - "Vision Sensor running - processing frames..."
   - "Web Dashboard thread started"

3. **Access the web dashboard**:
   - Open browser to: `http://localhost:5000` (or `http://[RPI_IP]:5000`)
   - Check the "Live Camera Feed" section

4. **If video feed still doesn't work**, check:

   a. **Browser Console** (F12 → Console):
      - Look for JavaScript errors
      - Check if video feed URL is accessible: `/video_feed`

   b. **Application Logs**:
      - Look for "Video feed error" messages
      - Check for "get_current_frame() returned None" warnings
      - Verify camera initialization messages

   c. **Camera Status**:
      ```bash
      python3 debugging_utils/diagnose_camera.py
      ```

   d. **Test Video Feed Directly**:
      - In browser, go to: `http://localhost:5000/video_feed`
      - Should see MJPEG stream (or error message)

## Common Issues

### Issue: Video feed shows "Camera Not Available"
**Solution**: 
- Check if camera is initialized: Look for "Camera initialized successfully" in logs
- Verify camera index: Try `python main.py --camera 0` or `--camera 1`
- Check camera permissions: `groups` (should include 'video')

### Issue: Video feed shows "No Frame Available"
**Solution**:
- This means `get_current_frame()` returned `None`
- Check if camera is actually working: `python3 debugging_utils/test_video_feed.py`
- Verify VisionSensor is running and processing frames
- Check logs for camera errors

### Issue: Video feed is blank/black
**Solution**:
- Camera might be working but no frames are being captured
- Check if another process is using the camera: `sudo lsof /dev/video0`
- Try restarting the application
- Verify camera is not covered or blocked

### Issue: Video feed works but no pose overlay
**Solution**:
- This is normal if no person is detected in frame
- Pose detection requires a person to be visible
- Make sure you're in front of the camera
- Check lighting conditions

## Additional Debugging

If issues persist, enable more detailed logging:

1. **Check video feed route directly**:
   ```bash
   curl http://localhost:5000/video_feed
   ```
   Should return binary MJPEG data (not text)

2. **Check if gesture_detector is initialized**:
   ```bash
   curl http://localhost:5000/api/status
   ```
   Look for `"camera_active": true`

3. **Monitor logs in real-time**:
   ```bash
   python main.py --camera 0 2>&1 | grep -i "camera\|video\|frame"
   ```

## Expected Behavior

After the fix:
- ✅ Video feed should show camera frames immediately
- ✅ Frames should have pose overlay when person is detected
- ✅ FPS counter should be visible
- ✅ No blank/black frames (unless camera is actually unavailable)

## Files Modified

1. `core/gestures.py` - Enhanced `get_current_frame()` method
2. `web/server.py` - Improved error handling and logging
3. `debugging_utils/test_video_feed.py` - New test script (created)
4. `debugging_utils/VIDEO_FEED_FIX.md` - This documentation (created)

