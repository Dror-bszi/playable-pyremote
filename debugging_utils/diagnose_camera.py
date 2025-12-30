#!/usr/bin/env python3
"""
Camera Diagnostic Script for Raspberry Pi

This script helps diagnose USB camera detection issues by checking:
1. USB device detection
2. Video device nodes
3. OpenCV camera access
4. Permissions
5. Camera capabilities
"""

import os
import sys
import subprocess
import cv2
from pathlib import Path


def print_section(title):
    """Print a formatted section header."""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def check_usb_devices():
    """Check USB devices connected to the system."""
    print_section("USB Devices")
    try:
        result = subprocess.run(
            ['lsusb'],
            capture_output=True,
            text=True,
            check=True
        )
        print(result.stdout)
        
        if 'camera' in result.stdout.lower() or 'video' in result.stdout.lower():
            print("\n✓ Camera-related USB device detected")
        else:
            print("\n⚠ No obvious camera device found in USB list")
            print("  (This doesn't mean there's no camera - check video devices)")
    except subprocess.CalledProcessError as e:
        print(f"Error running lsusb: {e}")
    except FileNotFoundError:
        print("lsusb not found - install with: sudo apt-get install usbutils")


def check_video_devices():
    """Check video device nodes in /dev."""
    print_section("Video Device Nodes")
    
    video_devices = []
    for i in range(10):  # Check /dev/video0 through /dev/video9
        dev_path = f"/dev/video{i}"
        if os.path.exists(dev_path):
            video_devices.append(dev_path)
            # Check permissions
            stat_info = os.stat(dev_path)
            mode = oct(stat_info.st_mode)[-3:]
            print(f"  {dev_path} - Mode: {mode}")
            
            # Check if readable
            if os.access(dev_path, os.R_OK):
                print(f"    ✓ Readable")
            else:
                print(f"    ✗ NOT readable (permission issue)")
            
            # Check if writable
            if os.access(dev_path, os.W_OK):
                print(f"    ✓ Writable")
            else:
                print(f"    ✗ NOT writable (may need to add user to video group)")
    
    if not video_devices:
        print("  ✗ No video devices found in /dev/video*")
        print("  This usually means:")
        print("    1. Camera is not connected")
        print("    2. Camera driver is not loaded")
        print("    3. Camera is not a UVC (USB Video Class) device")
    else:
        print(f"\n✓ Found {len(video_devices)} video device(s)")
    
    return video_devices


def check_v4l2_info(device_path):
    """Get detailed information about a video device using v4l2-ctl."""
    print_section(f"V4L2 Info for {device_path}")
    try:
        result = subprocess.run(
            ['v4l2-ctl', '--device', device_path, '--all'],
            capture_output=True,
            text=True,
            check=True
        )
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Error running v4l2-ctl: {e.stderr}")
        print("Install with: sudo apt-get install v4l-utils")
    except FileNotFoundError:
        print("v4l2-ctl not found - install with: sudo apt-get install v4l-utils")


def check_opencv_cameras():
    """Test OpenCV camera access for multiple indices."""
    print_section("OpenCV Camera Detection")
    
    available_cameras = []
    
    for i in range(5):  # Check camera indices 0-4
        print(f"\nTesting camera index {i}...")
        cap = cv2.VideoCapture(i)
        
        if cap.isOpened():
            # Try to read a frame to confirm it's working
            ret, frame = cap.read()
            if ret and frame is not None:
                height, width = frame.shape[:2]
                print(f"  ✓ Camera {i} is OPEN and working")
                print(f"    Resolution: {width}x{height}")
                
                # Get backend info
                backend = cap.getBackendName()
                print(f"    Backend: {backend}")
                
                # Get some properties
                fps = cap.get(cv2.CAP_PROP_FPS)
                print(f"    FPS: {fps}")
                
                available_cameras.append(i)
            else:
                print(f"  ⚠ Camera {i} opened but cannot read frames")
            cap.release()
        else:
            print(f"  ✗ Camera {i} cannot be opened")
    
    if available_cameras:
        print(f"\n✓ OpenCV found {len(available_cameras)} working camera(s) at index(es): {available_cameras}")
    else:
        print("\n✗ OpenCV cannot access any cameras")
        print("  Possible causes:")
        print("    1. No camera connected")
        print("    2. Camera not recognized by system")
        print("    3. Permission issues (user not in video group)")
        print("    4. Camera in use by another process")
    
    return available_cameras


def check_user_permissions():
    """Check if user has necessary permissions."""
    print_section("User Permissions")
    
    user = os.environ.get('USER', 'unknown')
    print(f"Current user: {user}")
    
    # Check groups
    try:
        result = subprocess.run(
            ['groups'],
            capture_output=True,
            text=True,
            check=True
        )
        groups = result.stdout.strip().split()
        print(f"User groups: {', '.join(groups)}")
        
        if 'video' in groups:
            print("  ✓ User is in 'video' group (good for camera access)")
        else:
            print("  ✗ User is NOT in 'video' group")
            print("    Fix with: sudo usermod -a -G video $USER")
            print("    Then log out and log back in")
    except Exception as e:
        print(f"Error checking groups: {e}")


def check_camera_processes():
    """Check if camera is being used by another process."""
    print_section("Camera Usage by Other Processes")
    
    try:
        # Check for processes using video devices
        result = subprocess.run(
            ['lsof', '/dev/video*'],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0 and result.stdout:
            print("Processes using video devices:")
            print(result.stdout)
        else:
            print("  ✓ No other processes appear to be using video devices")
    except FileNotFoundError:
        print("lsof not found - install with: sudo apt-get install lsof")
    except Exception as e:
        print(f"Error checking processes: {e}")


def check_kernel_modules():
    """Check if necessary kernel modules are loaded."""
    print_section("Kernel Modules")
    
    try:
        result = subprocess.run(
            ['lsmod'],
            capture_output=True,
            text=True,
            check=True
        )
        
        modules = result.stdout.lower()
        relevant_modules = []
        
        if 'uvcvideo' in modules:
            relevant_modules.append('uvcvideo (USB Video Class)')
        if 'videobuf2' in modules:
            relevant_modules.append('videobuf2 (Video buffer)')
        if 'videodev' in modules:
            relevant_modules.append('videodev (Video device)')
        
        if relevant_modules:
            print("Relevant kernel modules loaded:")
            for mod in relevant_modules:
                print(f"  ✓ {mod}")
        else:
            print("  ⚠ No obvious video-related modules found")
            print("  (This may be normal if modules are built into kernel)")
    except Exception as e:
        print(f"Error checking modules: {e}")


def main():
    """Run all diagnostic checks."""
    print("\n" + "=" * 60)
    print("  Raspberry Pi USB Camera Diagnostic Tool")
    print("=" * 60)
    
    # Run all checks
    check_usb_devices()
    video_devices = check_video_devices()
    
    if video_devices:
        # Get detailed info for first device
        check_v4l2_info(video_devices[0])
    
    check_user_permissions()
    check_kernel_modules()
    check_camera_processes()
    available_cameras = check_opencv_cameras()
    
    # Summary
    print_section("Summary & Recommendations")
    
    if available_cameras:
        print(f"✓ Camera is working! Use camera index: {available_cameras[0]}")
        print(f"\nTo use this camera in your application:")
        print(f"  python main.py --camera {available_cameras[0]}")
    else:
        print("✗ Camera is NOT accessible via OpenCV")
        print("\nTroubleshooting steps:")
        print("1. Verify camera is connected: lsusb")
        print("2. Check video devices exist: ls -l /dev/video*")
        print("3. Add user to video group: sudo usermod -a -G video $USER")
        print("4. Log out and log back in after adding to video group")
        print("5. Check if camera works: v4l2-ctl --device /dev/video0 --all")
        print("6. Try a different USB port (prefer USB 2.0 ports)")
        print("7. Check dmesg for errors: dmesg | tail -20")
    
    print("\n" + "=" * 60)


if __name__ == '__main__':
    main()



