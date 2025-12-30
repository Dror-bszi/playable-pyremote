#!/usr/bin/env python3
"""
Test script to verify video feed functionality.

This script tests if the camera and video feed are working correctly.
"""

import sys
import cv2
from core.gestures import GestureDetector

def test_camera_direct():
    """Test camera access directly."""
    print("=" * 60)
    print("Testing Camera Direct Access")
    print("=" * 60)
    
    try:
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("❌ Camera cannot be opened")
            return False
        
        ret, frame = cap.read()
        if not ret or frame is None:
            print("❌ Cannot read frames from camera")
            cap.release()
            return False
        
        print(f"✓ Camera working - Frame size: {frame.shape[1]}x{frame.shape[0]}")
        cap.release()
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_gesture_detector():
    """Test GestureDetector initialization and frame reading."""
    print("\n" + "=" * 60)
    print("Testing GestureDetector")
    print("=" * 60)
    
    try:
        print("Initializing GestureDetector...")
        detector = GestureDetector(camera_index=0)
        print("✓ GestureDetector initialized")
        
        print("Testing is_active()...")
        if detector.is_active():
            print("✓ Camera is active")
        else:
            print("❌ Camera is not active")
            return False
        
        print("Testing get_current_frame()...")
        frame = detector.get_current_frame()
        if frame is None:
            print("❌ get_current_frame() returned None")
            print("   This might be because no frames have been processed yet")
            print("   The updated code should read directly from camera...")
            return False
        
        print(f"✓ get_current_frame() working - Frame size: {frame.shape[1]}x{frame.shape[0]}")
        
        # Test processing a frame
        print("Testing process_frame()...")
        landmarks = detector.process_frame()
        if landmarks:
            print(f"✓ process_frame() working - Detected {len(landmarks.landmark)} landmarks")
        else:
            print("⚠ process_frame() returned None (no pose detected, but camera is working)")
        
        # Test get_current_frame() again after processing
        frame2 = detector.get_current_frame()
        if frame2 is not None:
            print(f"✓ get_current_frame() still working after process_frame()")
        else:
            print("❌ get_current_frame() failed after process_frame()")
            return False
        
        detector.cleanup()
        print("✓ GestureDetector cleanup successful")
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("  Video Feed Test Script")
    print("=" * 60)
    
    # Test 1: Direct camera access
    camera_ok = test_camera_direct()
    
    if not camera_ok:
        print("\n❌ Camera direct access failed - cannot proceed with GestureDetector test")
        print("\nTroubleshooting:")
        print("1. Check camera is connected: lsusb")
        print("2. Check video device exists: ls -l /dev/video*")
        print("3. Check permissions: groups (should include 'video')")
        print("4. Run: python3 debugging_utils/diagnose_camera.py")
        return 1
    
    # Test 2: GestureDetector
    detector_ok = test_gesture_detector()
    
    # Summary
    print("\n" + "=" * 60)
    print("  Test Summary")
    print("=" * 60)
    
    if camera_ok and detector_ok:
        print("✓ All tests passed!")
        print("\nThe video feed should work in the web server.")
        print("If it doesn't, check:")
        print("1. Is the application running? (python main.py)")
        print("2. Is the web server accessible? (http://localhost:5000)")
        print("3. Check browser console for errors")
        print("4. Check application logs for video feed errors")
        return 0
    else:
        print("❌ Some tests failed")
        print("\nPlease fix the issues above before using the video feed.")
        return 1


if __name__ == '__main__':
    sys.exit(main())

