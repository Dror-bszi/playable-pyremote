# Implementation Plan

- [x] 1. Set up project structure and configuration
  - Create directory structure for core/, web/, and config/
  - Create config/mappings.json with default gesture mappings and thresholds
  - Update requirements.txt with new dependencies (opencv-python, mediapipe, flask, flask-cors)
  - _Requirements: 8.3, 8.4_

- [x] 2. Implement MediaPipe gesture detection system
  - _Requirements: 1.1, 1.2, 1.3, 7.3_

- [x] 2.1 Create GestureDetector class in core/gestures.py
  - Initialize MediaPipe Pose with appropriate confidence thresholds
  - Implement camera capture initialization (support USB and Pi Camera)
  - Create method to process single frame and return pose landmarks
  - Implement landmark delta calculation between frames
  - Create method to get current frame with pose overlay for dashboard
  - _Requirements: 1.1, 1.2, 1.5, 5.1, 10.1_

- [x] 2.2 Implement gesture detection logic in GestureDetector
  - Create detect_gestures() method that compares landmarks against thresholds
  - Implement detection for: left_elbow_raise, right_elbow_raise, left_arm_forward, right_arm_forward
  - Return list of detected gestures with button mappings
  - Add threshold update method for real-time adjustment
  - _Requirements: 1.1, 1.2, 3.3, 10.2_

- [x] 2.3 Create GestureMapping class in core/mappings.py
  - Implement load_mappings() to read from config/mappings.json
  - Implement save_mappings() to persist configuration
  - Create add_mapping() and remove_mapping() methods
  - Implement get_active_mappings() to return current configuration
  - _Requirements: 4.1, 4.2, 4.5_

- [x] 3. Implement Vision Sensor pipe writer
  - _Requirements: 1.1, 1.4, 7.1, 7.3_

- [x] 3.1 Create vision_sensor.py with main loop
  - Initialize GestureDetector and GestureMapping
  - Open Named Pipe for writing (/tmp/my_pipe)
  - Implement main loop that processes frames at 30+ FPS
  - Track gesture state (active/inactive) to send press/release events only on state changes
  - _Requirements: 1.1, 1.5, 7.3_

- [x] 3.2 Implement pipe message writing in vision_sensor.py
  - Create write_button_event() function following Hardware Producer protocol
  - Format messages as: BUTTON_NAME\npress|release\n\n
  - Handle pipe write errors with retry logic
  - Add FPS monitoring and logging
  - _Requirements: 1.1, 7.1, 7.3_

- [x] 4. Refactor pyremoteplay to use PipeReader class
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 7.1, 7.2, 7.4_

- [x] 4.1 Create PipeReader class in pyremoteplay/pipe_reader.py
  - Implement __init__ with controller and pipe_path parameters
  - Create start() method to launch reader thread
  - Implement _read_loop() that continuously reads from pipe
  - Add stop() method for graceful shutdown
  - _Requirements: 2.1, 2.2, 7.2, 7.4_

- [x] 4.2 Implement pipe message parsing in PipeReader
  - Create _parse_message() to read 3-line protocol
  - Detect button messages (line2 = "press" or "release")
  - Detect analog messages (line2 = "x" or "y", line3 = float value)
  - Handle malformed messages gracefully
  - _Requirements: 2.1, 2.3, 2.4_

- [x] 4.3 Implement controller forwarding in PipeReader
  - Create _forward_to_controller() method
  - Call controller.button() for button events
  - Call controller.stick() for analog events
  - Add error handling and logging
  - _Requirements: 2.1, 2.3, 2.4, 7.2_

- [x] 4.4 Refactor pyremoteplay/__main__.py to use PipeReader
  - Remove inline pipe reading code from CLIInstance.run()
  - Import PipeReader class
  - Instantiate PipeReader after controller creation in worker() function
  - Start PipeReader thread before entering main event loop
  - Ensure PipeReader stops on session end
  - _Requirements: 2.1, 2.2, 7.2_

- [x] 5. Implement Web Dashboard Flask application
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.1.1-5.1.7_

- [x] 5.1 Create Flask app structure in web/server.py
  - Initialize Flask app with CORS support
  - Create shared state objects for GestureDetector and GestureMapping
  - Set up logging configuration
  - Define all API route handlers (status, thresholds, mappings, PSN, video feed)
  - _Requirements: 5.1, 5.2_

- [x] 5.2 Implement PSN connection management in web/server.py
  - Create PSNConnectionManager class to handle OAuth flow
  - Implement /api/psn/login endpoint to start OAuth and return authorization URL
  - Implement /api/psn/callback endpoint to process redirect URL and exchange code for tokens
  - Implement /api/psn/pin endpoint to submit PIN and complete registration
  - Implement /api/remoteplay/connect endpoint to start pyremoteplay subprocess
  - Implement /api/remoteplay/disconnect endpoint to stop pyremoteplay subprocess
  - Store tokens securely in config file
  - _Requirements: 5.1.1, 5.1.2, 5.1.3, 5.1.4, 5.1.5, 5.1.6, 5.1.7_

- [x] 5.3 Implement system status and configuration endpoints in web/server.py
  - Create /api/status endpoint returning controller_connected, ps5_connected, camera_active, active_mappings, psn_authenticated
  - Create /api/thresholds GET/POST endpoints for threshold management
  - Create /api/mappings GET/POST/DELETE endpoints for gesture mapping management
  - Integrate with GestureDetector and GestureMapping classes
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 4.5, 5.3, 5.4, 5.5_

- [x] 5.4 Implement video feed streaming in web/server.py
  - Create /video_feed endpoint
  - Get current frame from GestureDetector with pose overlay
  - Encode frame as JPEG
  - Return MJPEG stream with multipart/x-mixed-replace content type
  - Target 15+ FPS for dashboard display
  - _Requirements: 5.1, 5.2, 10.1, 10.2, 10.3, 10.4, 10.5_

- [x] 5.5 Create dashboard HTML template
  - Create web/templates/dashboard.html with complete UI structure
  - Add PSN Connection Panel with login button, redirect URL input, PIN input, connect/disconnect buttons
  - Add Status Panel showing PSN auth, PS5 connection, controller, camera, FPS
  - Add Video Feed section with img tag pointing to /video_feed
  - Add Threshold Controls with sliders for delta_threshold and raise_minimum
  - Add Gesture Mapping section with dropdowns and add/remove buttons
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.1.1-5.1.7_

- [x] 5.6 Create dashboard JavaScript and CSS
  - Create web/static/js/dashboard.js with PSN login flow, status polling, threshold updates, gesture mapping management
  - Create web/static/css/style.css with responsive styling for all dashboard components
  - Implement visual feedback for gesture detection events
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 10.3_

- [x] 6. Implement Main Orchestrator
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

- [x] 6.1 Create main.py with startup and shutdown
  - Create Named Pipe if it doesn't exist
  - Start Hardware Producer subprocess (./controller/build/detect_controller)
  - Initialize GestureDetector and GestureMapping instances
  - Start Vision Sensor thread with vision_sensor_loop()
  - Start Web Dashboard thread with Flask app
  - Implement signal handlers for SIGINT/SIGTERM
  - Implement cleanup() function to stop all threads and subprocesses gracefully
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

- [x] 7. Update documentation and installation
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 7.1 Create install.sh script
  - Add system dependency installation (libsdl2-dev, python3-opencv, cmake)
  - Add Python virtual environment setup
  - Install all Python dependencies from requirements.txt
  - Compile Hardware Producer (cd controller && mkdir build && cmake .. && make)
  - Create Named Pipe if it doesn't exist
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 6.1, 6.2_

- [x] 7.2 Update README.md with comprehensive documentation
  - Document system requirements (Raspberry Pi 4, camera, DualSense controller)
  - Document installation steps (run install.sh)
  - Document usage: python main.py
  - Document web dashboard access: http://localhost:5000
  - Document PSN authentication flow
  - Document gesture mapping configuration
  - Add troubleshooting section
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 9.1_

- [x] 8. Add comprehensive error handling
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 8.1 Add error handling to all components
  - Vision Sensor: camera not found retry, MediaPipe initialization failure, pipe write failures, FPS warnings
  - PipeReader: pipe read failures with reopen, invalid message formats, controller API errors
  - Web Dashboard: port already in use, camera access denied, subprocess crashes, UI error messages
  - Main Orchestrator: Hardware Producer crashes with restart, thread exceptions, shutdown timeout with force kill
  - _Requirements: 5.1, 5.2, 7.2, 7.3, 7.4, 9.5_

- [ ] 9. Implement WiFi Hotspot Fallback System
  - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8_

- [ ] 9.1 Create WiFiManager class in network/wifi_manager.py
  - Implement check_wifi_connection() to detect available known networks
  - Implement start_hotspot() using hostapd and dnsmasq
  - Implement stop_hotspot() to disable hotspot and return to client mode
  - Implement connect_to_wifi() to attempt connection to specified network
  - Implement save_wifi_credentials() to persist to wpa_supplicant.conf
  - Create _get_device_id() to generate unique SSID suffix from MAC address
  - _Requirements: 11.1, 11.2, 11.7, 11.8_

- [ ] 9.2 Create hotspot configuration files
  - Create config/hostapd.conf with SSID template, WPA2 security, channel 7
  - Create config/dnsmasq.conf with DHCP range 192.168.4.2-192.168.4.20
  - Set hotspot IP to 192.168.4.1
  - Set default password to "playable2024"
  - _Requirements: 11.2, 11.3, 11.4_

- [ ] 9.3 Add WiFi configuration endpoints to web/server.py
  - Implement /api/wifi/scan endpoint to return available networks with signal strength
  - Implement /api/wifi/connect endpoint to accept SSID and password, save credentials, attempt connection
  - Implement /api/wifi/status endpoint to return connection status, current SSID, IP address, hotspot status
  - Integrate with WiFiManager class
  - _Requirements: 11.4, 11.5, 11.6, 11.7_

- [ ] 9.4 Add WiFi configuration UI to dashboard
  - Create WiFi configuration panel in web/templates/dashboard.html
  - Add network scan button and network selection dropdown
  - Add password input field and connect button
  - Add WiFi status display showing connection state and current network
  - Create JavaScript functions in dashboard.js for scan, connect, status polling
  - Show WiFi panel prominently when in hotspot mode
  - _Requirements: 11.4, 11.5, 11.6_

- [ ] 9.5 Integrate WiFi manager into main.py startup
  - Import WiFiManager at startup
  - Check WiFi connection before starting other components
  - If no connection found, start hotspot mode and log hotspot SSID and IP
  - Pass WiFiManager instance to Web Dashboard for status monitoring
  - Add periodic WiFi connection check to detect network availability changes
  - _Requirements: 11.1, 11.7, 11.8_

- [ ] 9.6 Update install.sh for WiFi hotspot dependencies
  - Install hostapd and dnsmasq packages
  - Stop and disable hostapd and dnsmasq systemd services (managed by our script)
  - Copy hostapd.conf to /etc/hostapd/
  - Copy dnsmasq.conf to /etc/dnsmasq.conf
  - Create and enable playable-wifi.service systemd service
  - Set appropriate file permissions
  - _Requirements: 11.1, 11.2, 11.3_

- [ ] 9.7 Update README.md with WiFi setup documentation
  - Document default hotspot SSID format (PlayAble-Setup-XXXX)
  - Document default hotspot password
  - Document hotspot IP address (192.168.4.1)
  - Add step-by-step WiFi configuration instructions
  - Add troubleshooting section for WiFi connectivity issues
  - _Requirements: 11.2, 11.3, 11.4_

