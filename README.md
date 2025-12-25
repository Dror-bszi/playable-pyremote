# PlayAble - Rehabilitation Gaming System

PlayAble is a hybrid gesture-to-game control system designed for physical rehabilitation. The system enables specific PlayStation buttons to be triggered by body movements detected via computer vision while maintaining full functionality of a physical PS5 DualSense controller.

## Overview

PlayAble helps rehabilitation patients reconnect through gaming and movement by combining traditional controller input with therapeutic body movements. The system uses MediaPipe for pose detection, allowing therapists to map specific body movements (like arm raises or extensions) to PlayStation button presses.

### Key Features

- **Gesture-Based Controls**: Map body movements to PlayStation buttons using computer vision
- **Hybrid Input**: Use physical DualSense controller and gestures simultaneously
- **Real-Time Adjustment**: Adjust movement sensitivity thresholds during therapy sessions
- **Web Dashboard**: Monitor patient movements and configure the system via web interface
- **Low Latency**: End-to-end latency under 150ms for responsive gaming
- **Raspberry Pi Compatible**: Runs on affordable Raspberry Pi 4 hardware

## System Requirements

### Hardware

- **Raspberry Pi 4** (4GB RAM recommended) running 64-bit Raspberry Pi OS
- **Camera**: USB webcam or Raspberry Pi Camera Module
- **DualSense Controller**: Sony PlayStation 5 wireless controller
- **PS5 Console**: Connected to the same local network
- **Network**: Wired Ethernet connection recommended for lower latency

### Software

- Raspberry Pi OS (64-bit) or compatible Linux distribution
- Python 3.9 or higher
- SDL2 library
- CMake and build tools
- OpenCV and MediaPipe

## Installation

### Quick Install

Run the automated installation script:

```bash
chmod +x install.sh
./install.sh
```

The script will:
1. Install system dependencies (SDL2, OpenCV, CMake)
2. Create Python virtual environment
3. Install Python dependencies
4. Compile the Hardware Producer (C++ component)
5. Create the Named Pipe for inter-process communication

### Manual Installation

If you prefer to install manually:

1. **Install system dependencies:**
   ```bash
   sudo apt-get update
   sudo apt-get install -y libsdl2-dev python3-opencv cmake python3-venv python3-pip build-essential
   ```

2. **Create Python virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Compile Hardware Producer:**
   ```bash
   cd controller
   mkdir build && cd build
   cmake ..
   make
   cd ../..
   ```

5. **Create Named Pipe:**
   ```bash
   mkfifo /tmp/my_pipe
   chmod 666 /tmp/my_pipe
   ```

## Usage

### Starting the System

1. **Pair your DualSense controller** via Bluetooth:
   ```bash
   bluetoothctl
   scan on
   pair [CONTROLLER_MAC_ADDRESS]
   connect [CONTROLLER_MAC_ADDRESS]
   ```

2. **Connect your camera** (USB or Pi Camera)

3. **Activate virtual environment:**
   ```bash
   source venv/bin/activate
   ```

4. **Start PlayAble:**
   ```bash
   python main.py
   ```

The system will start three components:
- Hardware Producer (captures DualSense controller input)
- Vision Sensor (detects body movements via camera)
- Web Dashboard (monitoring and configuration interface)

### Accessing the Web Dashboard

Open your web browser and navigate to:
```
http://localhost:5000
```

Or from another device on the same network:
```
http://[RASPBERRY_PI_IP]:5000
```

## PSN Authentication and PS5 Connection

The web dashboard provides a complete interface for connecting to your PS5:

### Step 1: PSN Login

1. Click **"Start PSN Login"** in the PSN Connection Panel
2. The system will display a PlayStation Network authorization URL
3. Open the URL in a web browser and log in with your PSN account
4. After logging in, you'll be redirected to a blank page

### Step 2: Capture Redirect URL

1. Copy the entire URL from the browser's address bar (starts with `https://remoteplay.dl.playstation.net/remoteplay/redirect`)
2. Paste the URL into the **"Redirect URL"** field in the dashboard
3. Click **"Submit Redirect URL"**

### Step 3: Enter PIN Code

1. On your PS5, go to **Settings → System → Remote Play**
2. Enable Remote Play if not already enabled
3. Select **"Link Device"** to display a PIN code
4. Enter the PIN code in the dashboard's **"PIN Code"** field
5. Click **"Submit PIN"**

### Step 4: Connect to PS5

1. Once authenticated, click **"Connect to PS5"**
2. The system will start the Remote Play session
3. Connection status will update to show "PS5 Connected"

### Disconnecting

Click **"Disconnect from PS5"** to end the Remote Play session. Your authentication tokens are saved, so you won't need to repeat the PSN login process unless you clear the configuration.

## Gesture Mapping Configuration

### Available Gestures

- **Left Elbow Raise**: Raise left elbow upward
- **Right Elbow Raise**: Raise right elbow upward
- **Left Arm Forward**: Extend left arm toward camera
- **Right Arm Forward**: Extend right arm toward camera
- **Shoulder Shrug**: Raise both shoulders

### Available Buttons

- Face Buttons: CROSS, CIRCLE, SQUARE, TRIANGLE
- Shoulder Buttons: L1, R1, L2, R2

### Creating Gesture Mappings

1. In the **Gesture Mapping** section of the dashboard:
2. Select a gesture from the dropdown
3. Select a PlayStation button from the dropdown
4. Click **"Add Mapping"**
5. The gesture will now trigger the selected button when detected

### Adjusting Sensitivity

Use the **Threshold Controls** to adjust detection sensitivity:

- **Delta Threshold** (0.01 - 0.5): Speed of movement required to trigger detection
  - Lower values = more sensitive (detects slower movements)
  - Higher values = less sensitive (requires faster movements)

- **Raise Minimum** (0.0 - 1.0): Range of movement required to trigger detection
  - Lower values = smaller movements trigger detection
  - Higher values = larger movements required

Adjust these values based on the patient's physical capabilities and range of motion.

## System Architecture

PlayAble consists of four main components:

1. **Hardware Producer** (C++ SDL2): Captures physical DualSense controller input
2. **Vision Sensor** (Python MediaPipe): Detects body movements via camera
3. **Remote Play Client** (pyremoteplay): Communicates with PS5 console
4. **Web Dashboard** (Flask): Monitoring and configuration interface

All components communicate via a Named Pipe (`/tmp/my_pipe`) for low-latency data transfer.

## Troubleshooting

### Camera Not Detected

**Problem**: "Camera not found" error in logs

**Solutions**:
- Verify camera is connected: `ls /dev/video*`
- Check camera permissions: `sudo usermod -a -G video $USER`
- Try different camera index in `core/vision_sensor.py`
- For Pi Camera, enable camera interface: `sudo raspi-config` → Interface Options → Camera

### DualSense Controller Not Connecting

**Problem**: Controller not detected by Hardware Producer

**Solutions**:
- Verify Bluetooth pairing: `bluetoothctl devices`
- Check controller battery level
- Re-pair controller: Remove device and pair again
- Verify SDL2 can detect controller: `sdl2-jstest --list`

### PS5 Connection Failed

**Problem**: Cannot connect to PS5 via Remote Play

**Solutions**:
- Verify PS5 and Raspberry Pi are on same network
- Check PS5 Remote Play is enabled: Settings → System → Remote Play
- Verify network connectivity: `ping [PS5_IP_ADDRESS]`
- Check firewall settings on network router
- Try wired Ethernet connection instead of WiFi

### High Latency / Low FPS

**Problem**: System feels sluggish or camera feed is choppy

**Solutions**:
- Close other applications to free CPU resources
- Reduce camera resolution in `core/gestures.py`
- Use wired Ethernet instead of WiFi for PS5 connection
- Check CPU temperature: `vcgencmd measure_temp` (should be < 80°C)
- Verify adequate power supply (official Raspberry Pi power adapter recommended)

### Named Pipe Errors

**Problem**: "Pipe write failure" or "Pipe read failure" in logs

**Solutions**:
- Verify pipe exists: `ls -l /tmp/my_pipe`
- Recreate pipe: `rm /tmp/my_pipe && mkfifo /tmp/my_pipe && chmod 666 /tmp/my_pipe`
- Check pipe permissions: Should show `prw-rw-rw-`
- Restart the system: `python main.py`

### Web Dashboard Not Accessible

**Problem**: Cannot access dashboard at http://localhost:5000

**Solutions**:
- Verify Flask is running: Check console output for "Running on http://0.0.0.0:5000"
- Check if port is in use: `sudo lsof -i :5000`
- Try alternative port: Edit `web/server.py` to use different port
- Check firewall: `sudo ufw status`
- Access via IP address: `http://[RASPBERRY_PI_IP]:5000`

### Gestures Not Detected

**Problem**: Body movements not triggering button presses

**Solutions**:
- Check camera feed in dashboard shows pose skeleton overlay
- Verify gesture mappings are configured in dashboard
- Adjust Delta Threshold to lower value (more sensitive)
- Adjust Raise Minimum to lower value (smaller movements)
- Ensure adequate lighting for camera
- Stand at appropriate distance from camera (2-3 meters recommended)
- Verify MediaPipe is detecting landmarks (check console logs)

### PSN Authentication Fails

**Problem**: Cannot complete PSN login or PIN submission

**Solutions**:
- Verify internet connection on Raspberry Pi
- Check PSN account credentials are correct
- Ensure PS5 Remote Play is enabled on console
- Try generating new PIN code on PS5
- Clear stored tokens: Delete config files and restart authentication
- Check system time is correct: `date` (PSN requires accurate time)

## Configuration Files

### config/mappings.json

Stores gesture mappings and threshold settings:

```json
{
  "thresholds": {
    "delta_threshold": 0.05,
    "raise_minimum": 0.1
  },
  "mappings": {
    "left_elbow_raise": "SQUARE",
    "right_elbow_raise": "CIRCLE",
    "left_arm_forward": "L1",
    "right_arm_forward": "R1"
  }
}
```

Edit this file directly or use the web dashboard to modify settings.

## Known Issues

- **Simultaneous R2/L2 Input**: Minor delay when buttons pressed simultaneously with R2 or L2 triggers
- **Pi Camera Compatibility**: Some Pi Camera modules may require additional configuration
- **Network Latency**: WiFi connections may introduce additional latency (wired recommended)

## Development

### Project Structure

```
playable/
├── controller/          # Hardware Producer (C++ SDL2)
│   ├── main.cpp
│   └── CMakeLists.txt
├── core/               # Vision Sensor (Python)
│   ├── gestures.py     # MediaPipe gesture detection
│   ├── mappings.py     # Gesture mapping configuration
│   └── vision_sensor.py # Main vision loop
├── pyremoteplay/       # Remote Play client library
├── web/                # Web Dashboard (Flask)
│   ├── server.py
│   ├── templates/
│   └── static/
├── config/             # Configuration files
│   └── mappings.json
├── main.py             # Main orchestrator
├── requirements.txt    # Python dependencies
└── install.sh          # Installation script
```

### Contributing

This is a rehabilitation-focused project. When contributing, please consider:
- Accessibility for users with limited mobility
- Clear documentation for therapists and patients
- Low latency for responsive gaming experience
- Robust error handling for reliability

## License

[Add your license information here]

## Acknowledgments

- MediaPipe by Google for pose estimation
- pyremoteplay library for PS5 Remote Play communication
- SDL2 for controller input handling

## Support

For issues, questions, or feature requests, please [add contact information or issue tracker link]
