"""
Flask Web Dashboard for PlayAble Rehabilitation Controller System.

Provides web interface for:
- PSN authentication and Remote Play connection management
- System status monitoring
- Gesture detection threshold configuration
- Gesture-to-button mapping management
- Live camera feed with pose overlay
"""

import os
import json
import logging
import subprocess
import threading
import time
from typing import Optional, Dict, Any
from flask import Flask, render_template, request, jsonify, Response
from flask_cors import CORS
import cv2

# Import core components
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.gestures import GestureDetector
from core.mappings import GestureMapping

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Shared state objects (will be injected by main orchestrator)
gesture_detector: Optional[GestureDetector] = None
gesture_mapping: Optional[GestureMapping] = None
psn_connection_manager: Optional['PSNConnectionManager'] = None


class PSNConnectionManager:
    """Manages PSN authentication and Remote Play connection lifecycle."""
    
    def __init__(self, config_file='config/psn_tokens.json'):
        self.config_file = config_file
        self.tokens = self._load_tokens()
        self.remoteplay_process: Optional[subprocess.Popen] = None
        self.is_authenticated = self.tokens is not None
        self.is_connected = False
        self._lock = threading.Lock()
        
        logger.info("PSNConnectionManager initialized")
    
    def _load_tokens(self) -> Optional[Dict[str, str]]:
        """Load stored PSN tokens from config file."""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load PSN tokens: {e}")
        return None
    
    def _save_tokens(self, tokens: Dict[str, str]):
        """Save PSN tokens to config file."""
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, 'w') as f:
                json.dump(tokens, f, indent=2)
            self.tokens = tokens
            self.is_authenticated = True
            logger.info("PSN tokens saved successfully")
        except Exception as e:
            logger.error(f"Failed to save PSN tokens: {e}")
            raise
    
    def start_oauth_flow(self) -> str:
        """
        Initiate PSN OAuth flow.
        Returns authorization URL for user to visit.
        """
        try:
            from pyremoteplay.oauth import OAuth
            oauth = OAuth()
            auth_url = oauth.get_authorization_url()
            logger.info("OAuth flow started")
            return auth_url
        except Exception as e:
            logger.error(f"Failed to start OAuth flow: {e}")
            raise
    
    def handle_redirect(self, redirect_url: str) -> Dict[str, str]:
        """
        Process OAuth redirect URL and exchange code for tokens.
        """
        try:
            from pyremoteplay.oauth import OAuth
            oauth = OAuth()
            code = oauth.extract_code(redirect_url)
            tokens = oauth.get_tokens(code)
            self._save_tokens(tokens)
            logger.info("OAuth tokens obtained successfully")
            return tokens
        except Exception as e:
            logger.error(f"Failed to handle OAuth redirect: {e}")
            raise
    
    def register_device(self, pin: str) -> bool:
        """
        Register device with PS5 using PIN code.
        """
        try:
            from pyremoteplay.register import register
            if not self.tokens:
                raise ValueError("No authentication tokens available")
            
            register(self.tokens, pin)
            logger.info("Device registered successfully with PS5")
            return True
        except Exception as e:
            logger.error(f"Failed to register device: {e}")
            raise
    
    def start_remoteplay(self, ps5_host: str = None) -> bool:
        """
        Start pyremoteplay subprocess with error handling.
        """
        with self._lock:
            if self.remoteplay_process and self.remoteplay_process.poll() is None:
                logger.warning("Remote Play already running")
                return False
            
            try:
                if not self.tokens:
                    raise ValueError("No authentication tokens available. Please authenticate first.")
                
                # Build command
                cmd = ['python', '-m', 'pyremoteplay']
                if ps5_host:
                    cmd.append(ps5_host)
                
                # Set environment with tokens
                env = os.environ.copy()
                env['PSN_TOKEN'] = json.dumps(self.tokens)
                
                # Start subprocess
                self.remoteplay_process = subprocess.Popen(
                    cmd,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                
                # Wait briefly to check if process starts successfully
                time.sleep(2)
                
                if self.remoteplay_process.poll() is not None:
                    # Process terminated immediately
                    stdout, stderr = self.remoteplay_process.communicate()
                    logger.error("Remote Play failed to start")
                    logger.error(f"STDOUT: {stdout.decode() if stdout else 'None'}")
                    logger.error(f"STDERR: {stderr.decode() if stderr else 'None'}")
                    self.remoteplay_process = None
                    self.is_connected = False
                    raise RuntimeError("Remote Play subprocess crashed immediately after start")
                
                self.is_connected = True
                logger.info(f"Remote Play started (PID: {self.remoteplay_process.pid})")
                return True
                
            except FileNotFoundError:
                logger.error("pyremoteplay module not found. Please ensure it's installed.")
                self.is_connected = False
                raise
            except ValueError as ve:
                logger.error(f"Configuration error: {ve}")
                self.is_connected = False
                raise
            except Exception as e:
                logger.error(f"Failed to start Remote Play: {e}", exc_info=True)
                self.is_connected = False
                raise
    
    def stop_remoteplay(self) -> bool:
        """
        Stop pyremoteplay subprocess gracefully.
        """
        with self._lock:
            if not self.remoteplay_process:
                logger.warning("No Remote Play process to stop")
                return False
            
            try:
                # Terminate gracefully
                self.remoteplay_process.terminate()
                
                # Wait up to 5 seconds
                try:
                    self.remoteplay_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # Force kill if still running
                    logger.warning("Remote Play did not terminate, forcing kill")
                    self.remoteplay_process.kill()
                    self.remoteplay_process.wait()
                
                self.is_connected = False
                self.remoteplay_process = None
                logger.info("Remote Play stopped")
                return True
                
            except Exception as e:
                logger.error(f"Failed to stop Remote Play: {e}")
                raise
    
    def get_status(self) -> Dict[str, Any]:
        """Get current connection status."""
        # Check if process is still running
        if self.remoteplay_process:
            if self.remoteplay_process.poll() is not None:
                # Process has terminated
                self.is_connected = False
                self.remoteplay_process = None
        
        return {
            'authenticated': self.is_authenticated,
            'connected': self.is_connected,
            'process_running': self.remoteplay_process is not None
        }


def init_app(detector: GestureDetector, mapping: GestureMapping):
    """
    Initialize Flask app with shared state objects.
    Called by main orchestrator.
    """
    global gesture_detector, gesture_mapping, psn_connection_manager
    
    gesture_detector = detector
    gesture_mapping = mapping
    psn_connection_manager = PSNConnectionManager()
    
    logger.info("Flask app initialized with shared state")


# Route handlers will be defined in subsequent subtasks
@app.route('/')
def dashboard():
    """Serve main dashboard page."""
    return render_template('dashboard.html')


@app.route('/api/status')
def get_status():
    """
    Return system status JSON.
    Includes controller, PS5, camera, mappings, and PSN authentication status.
    """
    try:
        status = {
            'controller_connected': False,  # Hardware Producer status (check pipe)
            'ps5_connected': False,
            'camera_active': False,
            'active_mappings': {},
            'psn_authenticated': False,
            'fps': 0.0
        }
        
        # Check PSN connection status
        if psn_connection_manager:
            psn_status = psn_connection_manager.get_status()
            status['psn_authenticated'] = psn_status['authenticated']
            status['ps5_connected'] = psn_status['connected']
        
        # Check camera status
        if gesture_detector:
            status['camera_active'] = gesture_detector.is_active()
            status['fps'] = gesture_detector.get_fps()
        
        # Get active mappings
        if gesture_mapping:
            status['active_mappings'] = gesture_mapping.get_active_mappings()
        
        # Check controller connection (check if pipe exists and is being written to)
        pipe_path = '/tmp/my_pipe'
        status['controller_connected'] = os.path.exists(pipe_path)
        
        return jsonify(status)
    except Exception as e:
        logger.error(f"Status endpoint error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/psn/login', methods=['POST'])
def psn_login():
    """
    Initiate PSN OAuth flow.
    Returns authorization URL for user to visit.
    """
    try:
        if not psn_connection_manager:
            return jsonify({'error': 'PSN connection manager not initialized'}), 500
        
        auth_url = psn_connection_manager.start_oauth_flow()
        return jsonify({
            'success': True,
            'authorization_url': auth_url
        })
    except Exception as e:
        logger.error(f"PSN login error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/psn/callback', methods=['POST'])
def psn_callback():
    """
    Handle OAuth redirect URL.
    Extracts code and exchanges for tokens.
    """
    try:
        if not psn_connection_manager:
            return jsonify({'error': 'PSN connection manager not initialized'}), 500
        
        data = request.get_json()
        redirect_url = data.get('redirect_url')
        
        if not redirect_url:
            return jsonify({'error': 'redirect_url is required'}), 400
        
        tokens = psn_connection_manager.handle_redirect(redirect_url)
        return jsonify({
            'success': True,
            'message': 'Authentication successful',
            'authenticated': True
        })
    except Exception as e:
        logger.error(f"PSN callback error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/psn/pin', methods=['POST'])
def submit_pin():
    """
    Submit Remote Play PIN code to complete device registration.
    """
    try:
        if not psn_connection_manager:
            return jsonify({'error': 'PSN connection manager not initialized'}), 500
        
        data = request.get_json()
        pin = data.get('pin')
        
        if not pin:
            return jsonify({'error': 'pin is required'}), 400
        
        success = psn_connection_manager.register_device(pin)
        return jsonify({
            'success': success,
            'message': 'Device registered successfully'
        })
    except Exception as e:
        logger.error(f"PIN submission error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/remoteplay/connect', methods=['POST'])
def connect_remoteplay():
    """
    Start Remote Play session.
    Optionally accepts ps5_host parameter.
    """
    try:
        if not psn_connection_manager:
            return jsonify({'error': 'PSN connection manager not initialized'}), 500
        
        data = request.get_json() or {}
        ps5_host = data.get('ps5_host')
        
        success = psn_connection_manager.start_remoteplay(ps5_host)
        return jsonify({
            'success': success,
            'message': 'Remote Play started',
            'connected': True
        })
    except Exception as e:
        logger.error(f"Remote Play connect error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/remoteplay/disconnect', methods=['POST'])
def disconnect_remoteplay():
    """
    Stop Remote Play session gracefully.
    """
    try:
        if not psn_connection_manager:
            return jsonify({'error': 'PSN connection manager not initialized'}), 500
        
        success = psn_connection_manager.stop_remoteplay()
        return jsonify({
            'success': success,
            'message': 'Remote Play stopped',
            'connected': False
        })
    except Exception as e:
        logger.error(f"Remote Play disconnect error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/thresholds', methods=['GET', 'POST'])
def thresholds():
    """
    Get or update detection thresholds.
    GET: Returns current threshold values
    POST: Updates threshold values
    """
    if request.method == 'GET':
        try:
            if not gesture_detector:
                return jsonify({'error': 'Gesture detector not initialized'}), 500
            
            current_thresholds = gesture_detector.get_thresholds()
            return jsonify(current_thresholds)
        except Exception as e:
            logger.error(f"Get thresholds error: {e}")
            return jsonify({'error': str(e)}), 500
    
    elif request.method == 'POST':
        try:
            if not gesture_detector:
                return jsonify({'error': 'Gesture detector not initialized'}), 500
            
            data = request.get_json()
            delta_threshold = data.get('delta_threshold')
            raise_minimum = data.get('raise_minimum')
            
            if delta_threshold is None or raise_minimum is None:
                return jsonify({'error': 'delta_threshold and raise_minimum are required'}), 400
            
            # Validate ranges
            if not (0.01 <= delta_threshold <= 2.0):
                return jsonify({'error': 'delta_threshold must be between 0.01 and 2.0'}), 400
            
            if not (0.0 <= raise_minimum <= 1.0):
                return jsonify({'error': 'raise_minimum must be between 0.0 and 1.0'}), 400
            
            gesture_detector.update_thresholds(delta_threshold, raise_minimum)
            
            return jsonify({
                'success': True,
                'message': 'Thresholds updated',
                'thresholds': {
                    'delta_threshold': delta_threshold,
                    'raise_minimum': raise_minimum
                }
            })
        except Exception as e:
            logger.error(f"Update thresholds error: {e}")
            return jsonify({'error': str(e)}), 500


@app.route('/api/mappings', methods=['GET', 'POST', 'DELETE'])
def mappings():
    """
    Manage gesture mappings.
    GET: Returns all active mappings
    POST: Add or update a mapping
    DELETE: Remove a mapping
    """
    if request.method == 'GET':
        try:
            if not gesture_mapping:
                return jsonify({'error': 'Gesture mapping not initialized'}), 500
            
            active_mappings = gesture_mapping.get_active_mappings()
            return jsonify(active_mappings)
        except Exception as e:
            logger.error(f"Get mappings error: {e}")
            return jsonify({'error': str(e)}), 500
    
    elif request.method == 'POST':
        try:
            if not gesture_mapping:
                return jsonify({'error': 'Gesture mapping not initialized'}), 500
            
            data = request.get_json()
            gesture_name = data.get('gesture_name')
            button = data.get('button')
            
            if not gesture_name or not button:
                return jsonify({'error': 'gesture_name and button are required'}), 400
            
            # Validate button name
            valid_buttons = ['CROSS', 'CIRCLE', 'SQUARE', 'TRIANGLE', 'R1', 'R2', 'L1', 'L2']
            if button not in valid_buttons:
                return jsonify({'error': f'button must be one of {valid_buttons}'}), 400
            
            gesture_mapping.add_mapping(gesture_name, button)
            
            return jsonify({
                'success': True,
                'message': 'Mapping added',
                'mapping': {
                    'gesture_name': gesture_name,
                    'button': button
                }
            })
        except Exception as e:
            logger.error(f"Add mapping error: {e}")
            return jsonify({'error': str(e)}), 500
    
    elif request.method == 'DELETE':
        try:
            if not gesture_mapping:
                return jsonify({'error': 'Gesture mapping not initialized'}), 500
            
            data = request.get_json()
            gesture_name = data.get('gesture_name')
            
            if not gesture_name:
                return jsonify({'error': 'gesture_name is required'}), 400
            
            gesture_mapping.remove_mapping(gesture_name)
            
            return jsonify({
                'success': True,
                'message': 'Mapping removed',
                'gesture_name': gesture_name
            })
        except Exception as e:
            logger.error(f"Remove mapping error: {e}")
            return jsonify({'error': str(e)}), 500


@app.route('/video_feed')
def video_feed():
    """
    Stream camera feed with pose overlay as MJPEG with error handling.
    Returns multipart/x-mixed-replace stream for real-time video.
    """
    def generate_frames():
        """Generator function that yields JPEG frames with error recovery."""
        consecutive_errors = 0
        max_consecutive_errors = 10
        
        while True:
            try:
                if not gesture_detector:
                    # Return blank frame if detector not initialized
                    blank = cv2.imencode('.jpg', cv2.zeros((480, 640, 3), dtype='uint8'))[1].tobytes()
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + blank + b'\r\n')
                    time.sleep(0.1)
                    consecutive_errors = 0
                    continue
                
                # Check if camera is accessible
                if not gesture_detector.is_active():
                    logger.warning("Camera not active in video feed")
                    # Return error frame
                    error_frame = cv2.zeros((480, 640, 3), dtype='uint8')
                    cv2.putText(
                        error_frame,
                        "Camera Not Available",
                        (150, 240),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        1,
                        (0, 0, 255),
                        2
                    )
                    error_bytes = cv2.imencode('.jpg', error_frame)[1].tobytes()
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + error_bytes + b'\r\n')
                    time.sleep(0.5)
                    consecutive_errors += 1
                    
                    if consecutive_errors >= max_consecutive_errors:
                        logger.error("Camera access denied or unavailable for extended period")
                        break
                    continue
                
                # Get current frame with pose overlay
                frame = gesture_detector.get_current_frame()
                
                if frame is None:
                    # Return blank frame if no frame available
                    blank = cv2.imencode('.jpg', cv2.zeros((480, 640, 3), dtype='uint8'))[1].tobytes()
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + blank + b'\r\n')
                    time.sleep(0.1)
                    consecutive_errors += 1
                    
                    if consecutive_errors >= max_consecutive_errors:
                        logger.error("Failed to get camera frames for extended period")
                        break
                    continue
                
                # Encode frame as JPEG
                ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                if not ret:
                    consecutive_errors += 1
                    continue
                
                frame_bytes = buffer.tobytes()
                
                # Yield frame in multipart format
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                
                # Reset error counter on success
                consecutive_errors = 0
                
                # Target 15 FPS for dashboard (66ms per frame)
                time.sleep(0.066)
                
            except cv2.error as cv_error:
                logger.error(f"OpenCV error in video feed: {cv_error}")
                consecutive_errors += 1
                time.sleep(0.1)
                
                if consecutive_errors >= max_consecutive_errors:
                    logger.error("Too many OpenCV errors, stopping video feed")
                    break
            except Exception as e:
                logger.error(f"Video feed error: {e}", exc_info=True)
                consecutive_errors += 1
                time.sleep(0.1)
                
                if consecutive_errors >= max_consecutive_errors:
                    logger.error("Too many errors, stopping video feed")
                    break
    
    return Response(
        generate_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


def run_server(host='0.0.0.0', port=5000):
    """
    Run Flask development server with error handling for port conflicts.
    Called by main orchestrator in a separate thread.
    """
    max_port_attempts = 5
    current_port = port
    
    for attempt in range(max_port_attempts):
        try:
            logger.info(f"Starting Flask server on {host}:{current_port}")
            app.run(host=host, port=current_port, debug=False, threaded=True)
            return  # Success
        except OSError as e:
            if 'Address already in use' in str(e) or 'Errno 48' in str(e):
                logger.warning(f"Port {current_port} already in use")
                if attempt < max_port_attempts - 1:
                    current_port += 1
                    logger.info(f"Trying alternative port: {current_port}")
                else:
                    logger.error(f"Failed to find available port after {max_port_attempts} attempts")
                    raise RuntimeError(
                        f"Could not start web server - ports {port} to {current_port} are in use. "
                        "Please stop other services or specify a different port."
                    )
            else:
                logger.error(f"Flask server error: {e}")
                raise
        except Exception as e:
            logger.error(f"Flask server error: {e}", exc_info=True)
            raise


if __name__ == '__main__':
    # For testing purposes only
    logger.warning("Running Flask app directly - shared state will not be initialized")
    run_server()
