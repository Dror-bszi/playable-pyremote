#!/usr/bin/env python3
"""
PlayAble Main Orchestrator

Coordinates all system components:
- Hardware Producer (C++ SDL2 subprocess)
- Vision Sensor (Python MediaPipe thread)
- Web Dashboard (Flask thread)
- Named Pipe creation and management

This is the single entry point for starting the PlayAble rehabilitation gaming system.
"""

import os
import sys
import time
import signal
import logging
import logging.handlers
import threading
import subprocess
from typing import Optional
from datetime import datetime

# Import core components
from core.gestures import GestureDetector
from core.mappings import GestureMapping
from core.vision_sensor import VisionSensor
from web.server import init_app, run_server


def setup_logging():
    """
    Configure logging to both console and run.log file.
    Aggregates all runs into run.log file.
    """
    log_file = 'run.log'
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()
    
    # Create formatter
    formatter = logging.Formatter(log_format, datefmt=date_format)
    
    # File handler - append mode to aggregate all runs
    file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    
    # Console handler - for terminal output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    
    # Add handlers to root logger
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    # Log session start
    logger = logging.getLogger(__name__)
    logger.info("=" * 80)
    logger.info(f"NEW SESSION STARTED - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 80)


# Setup logging first, before any other modules
setup_logging()
logger = logging.getLogger(__name__)


class PlayAbleOrchestrator:
    """Main orchestrator for the PlayAble rehabilitation gaming system."""
    
    def __init__(self, pipe_path: str = '/tmp/my_pipe', camera_index: int = 0):
        """
        Initialize orchestrator.
        
        Args:
            pipe_path: Path to Named Pipe for inter-process communication
            camera_index: Camera device index
        """
        self.pipe_path = pipe_path
        self.camera_index = camera_index
        
        # Component references
        self.hardware_producer_process: Optional[subprocess.Popen] = None
        self.vision_sensor: Optional[VisionSensor] = None
        self.vision_sensor_thread: Optional[threading.Thread] = None
        self.web_dashboard_thread: Optional[threading.Thread] = None
        
        # Shared state objects
        self.gesture_detector: Optional[GestureDetector] = None
        self.gesture_mapping: Optional[GestureMapping] = None
        
        # Running state
        self.running = False
        
        # Register signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        logger.info("PlayAble Orchestrator initialized")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        signal_name = 'SIGINT' if signum == signal.SIGINT else 'SIGTERM'
        logger.info(f"Received {signal_name}, initiating graceful shutdown...")
        self.stop()
    
    def create_named_pipe(self):
        """Create Named Pipe if it doesn't exist."""
        try:
            if os.path.exists(self.pipe_path):
                # Check if it's actually a FIFO
                if not os.stat(self.pipe_path).st_mode & 0o010000:
                    logger.warning(f"{self.pipe_path} exists but is not a FIFO, removing...")
                    os.remove(self.pipe_path)
                    os.mkfifo(self.pipe_path)
                else:
                    logger.info(f"Named Pipe already exists: {self.pipe_path}")
            else:
                logger.info(f"Creating Named Pipe: {self.pipe_path}")
                os.mkfifo(self.pipe_path)
            
            # Set permissions to allow read/write for all users
            os.chmod(self.pipe_path, 0o666)
            logger.info(f"Named Pipe ready: {self.pipe_path}")
            
        except Exception as e:
            logger.error(f"Failed to create Named Pipe: {e}")
            raise
    
    def start_hardware_producer(self):
        """Start Hardware Producer subprocess with validation."""
        try:
            hardware_producer_path = './controller/build/detect_controller'
            
            # Check if binary exists
            if not os.path.exists(hardware_producer_path):
                logger.error(f"Hardware Producer binary not found: {hardware_producer_path}")
                logger.error("Please compile the Hardware Producer first:")
                logger.error("  cd controller && mkdir -p build && cd build && cmake .. && make")
                raise FileNotFoundError(f"Hardware Producer binary not found: {hardware_producer_path}")
            
            # Check if binary is executable
            if not os.access(hardware_producer_path, os.X_OK):
                logger.error(f"Hardware Producer binary is not executable: {hardware_producer_path}")
                logger.info("Attempting to make it executable...")
                try:
                    os.chmod(hardware_producer_path, 0o755)
                    logger.info("Binary made executable")
                except Exception as chmod_error:
                    logger.error(f"Failed to make binary executable: {chmod_error}")
                    raise
            
            logger.info("Starting Hardware Producer subprocess...")
            
            # Start subprocess
            self.hardware_producer_process = subprocess.Popen(
                [hardware_producer_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            logger.info(f"Hardware Producer started (PID: {self.hardware_producer_process.pid})")
            
            # Give it a moment to initialize
            time.sleep(1)
            
            # Check if it's still running
            if self.hardware_producer_process.poll() is not None:
                # Process has already terminated
                stdout, stderr = self.hardware_producer_process.communicate()
                logger.error("Hardware Producer terminated immediately")
                logger.error(f"STDOUT: {stdout}")
                logger.error(f"STDERR: {stderr}")
                raise RuntimeError(
                    "Hardware Producer failed to start. "
                    "Please check that SDL2 is installed and a DualSense controller is connected."
                )
            
            logger.info("Hardware Producer running successfully")
            
        except FileNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to start Hardware Producer: {e}", exc_info=True)
            raise
    
    def initialize_shared_state(self):
        """Initialize shared state objects for gesture detection and mapping with error handling."""
        try:
            logger.info("Initializing shared state objects...")
            
            # Initialize GestureDetector
            logger.info("Creating GestureDetector...")
            try:
                self.gesture_detector = GestureDetector(camera_index=self.camera_index)
            except RuntimeError as camera_error:
                logger.error(f"Camera initialization failed: {camera_error}")
                logger.error(
                    f"Please check that camera at index {self.camera_index} is connected "
                    "and not in use by another application."
                )
                raise
            except ImportError as import_error:
                logger.error(f"Failed to import required modules: {import_error}")
                logger.error("Please ensure all dependencies are installed: pip install -r requirements.txt")
                raise
            
            # Initialize GestureMapping
            logger.info("Creating GestureMapping...")
            try:
                self.gesture_mapping = GestureMapping()
            except FileNotFoundError as config_error:
                logger.warning(f"Configuration file not found: {config_error}")
                logger.info("Creating default configuration...")
                # GestureMapping should handle this internally, but log it
            except Exception as mapping_error:
                logger.error(f"Failed to initialize GestureMapping: {mapping_error}")
                raise
            
            logger.info("Shared state initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize shared state: {e}", exc_info=True)
            raise
    
    def start_vision_sensor(self):
        """Start Vision Sensor in dedicated thread with error handling."""
        try:
            logger.info("Starting Vision Sensor thread...")
            
            # Create VisionSensor instance with shared gesture detector and mapping
            # This avoids opening the camera twice (camera is already open in gesture_detector)
            self.vision_sensor = VisionSensor(
                pipe_path=self.pipe_path,
                camera_index=self.camera_index,
                gesture_detector=self.gesture_detector,
                gesture_mapping=self.gesture_mapping
            )
            
            # Start in dedicated thread
            self.vision_sensor_thread = threading.Thread(
                target=self._vision_sensor_wrapper,
                name='VisionSensorThread',
                daemon=True
            )
            self.vision_sensor_thread.start()
            
            # Wait briefly to check if thread starts successfully
            time.sleep(1)
            
            if not self.vision_sensor_thread.is_alive():
                raise RuntimeError("Vision Sensor thread failed to start")
            
            logger.info("Vision Sensor thread started")
            
        except Exception as e:
            logger.error(f"Failed to start Vision Sensor: {e}", exc_info=True)
            raise
    
    def _vision_sensor_wrapper(self):
        """Wrapper for Vision Sensor with exception handling."""
        try:
            self.vision_sensor.run()
        except Exception as e:
            logger.error(f"Vision Sensor thread exception: {e}", exc_info=True)
            logger.error("Vision Sensor has stopped due to an error")
    
    def start_web_dashboard(self):
        """Start Web Dashboard in dedicated thread with error handling."""
        try:
            logger.info("Starting Web Dashboard thread...")
            
            # Initialize Flask app with shared state
            init_app(self.gesture_detector, self.gesture_mapping)
            
            # Start Flask server in dedicated thread
            self.web_dashboard_thread = threading.Thread(
                target=self._web_dashboard_wrapper,
                kwargs={'host': '0.0.0.0', 'port': 5000},
                name='WebDashboardThread',
                daemon=True
            )
            self.web_dashboard_thread.start()
            
            # Wait briefly to check if thread starts successfully
            time.sleep(1)
            
            if not self.web_dashboard_thread.is_alive():
                raise RuntimeError("Web Dashboard thread failed to start")
            
            logger.info("Web Dashboard thread started")
            logger.info("Dashboard available at: http://localhost:5000")
            
        except Exception as e:
            logger.error(f"Failed to start Web Dashboard: {e}", exc_info=True)
            raise
    
    def _web_dashboard_wrapper(self, host='0.0.0.0', port=5000):
        """Wrapper for Web Dashboard with exception handling."""
        try:
            run_server(host=host, port=port)
        except Exception as e:
            logger.error(f"Web Dashboard thread exception: {e}", exc_info=True)
            logger.error("Web Dashboard has stopped due to an error")
    
    def start(self):
        """Start all system components in the correct order."""
        try:
            logger.info("=" * 60)
            logger.info("Starting PlayAble Rehabilitation Gaming System")
            logger.info("=" * 60)
            
            # 1. Create Named Pipe
            logger.info("\n[1/5] Creating Named Pipe...")
            self.create_named_pipe()
            
            # 2. Start Hardware Producer
            logger.info("\n[2/5] Starting Hardware Producer...")
            self.start_hardware_producer()
            
            # 3. Initialize shared state
            logger.info("\n[3/5] Initializing shared state...")
            self.initialize_shared_state()
            
            # 4. Start Vision Sensor
            logger.info("\n[4/5] Starting Vision Sensor...")
            self.start_vision_sensor()
            
            # 5. Start Web Dashboard
            logger.info("\n[5/5] Starting Web Dashboard...")
            self.start_web_dashboard()
            
            self.running = True
            
            logger.info("\n" + "=" * 60)
            logger.info("PlayAble System Started Successfully!")
            logger.info("=" * 60)
            logger.info("\nSystem Status:")
            logger.info(f"  - Hardware Producer: Running (PID {self.hardware_producer_process.pid})")
            logger.info(f"  - Vision Sensor: Running")
            logger.info(f"  - Web Dashboard: Running (http://localhost:5000)")
            logger.info(f"  - Named Pipe: {self.pipe_path}")
            logger.info("\nPress Ctrl+C to stop the system")
            logger.info("=" * 60 + "\n")
            
        except Exception as e:
            logger.error(f"Failed to start PlayAble system: {e}")
            self.cleanup()
            raise
    
    def monitor_components(self):
        """Monitor component health and restart if necessary with improved error handling."""
        hardware_producer_restart_count = 0
        max_hardware_producer_restarts = 3
        vision_sensor_restart_count = 0
        max_vision_sensor_restarts = 3
        web_dashboard_restart_count = 0
        max_web_dashboard_restarts = 3
        
        while self.running:
            try:
                # Check Hardware Producer
                if self.hardware_producer_process:
                    if self.hardware_producer_process.poll() is not None:
                        logger.error("Hardware Producer has crashed!")
                        
                        # Get output for debugging
                        try:
                            stdout, stderr = self.hardware_producer_process.communicate(timeout=1)
                            logger.error(f"STDOUT: {stdout}")
                            logger.error(f"STDERR: {stderr}")
                        except subprocess.TimeoutExpired:
                            logger.warning("Could not retrieve Hardware Producer output")
                        
                        # Attempt restart if under limit
                        if hardware_producer_restart_count < max_hardware_producer_restarts:
                            hardware_producer_restart_count += 1
                            logger.info(
                                f"Attempting to restart Hardware Producer "
                                f"({hardware_producer_restart_count}/{max_hardware_producer_restarts})..."
                            )
                            try:
                                time.sleep(2)  # Wait before restart
                                self.start_hardware_producer()
                                logger.info("Hardware Producer restarted successfully")
                                hardware_producer_restart_count = 0  # Reset on success
                            except Exception as e:
                                logger.error(f"Failed to restart Hardware Producer: {e}")
                                if hardware_producer_restart_count >= max_hardware_producer_restarts:
                                    logger.error(
                                        "Maximum restart attempts reached for Hardware Producer. "
                                        "System may not function correctly."
                                    )
                        else:
                            logger.error(
                                "Hardware Producer has crashed too many times. "
                                "Not attempting further restarts."
                            )
                
                # Check Vision Sensor thread
                if self.vision_sensor_thread and not self.vision_sensor_thread.is_alive():
                    logger.error("Vision Sensor thread has died!")
                    
                    if vision_sensor_restart_count < max_vision_sensor_restarts:
                        vision_sensor_restart_count += 1
                        logger.info(
                            f"Attempting to restart Vision Sensor "
                            f"({vision_sensor_restart_count}/{max_vision_sensor_restarts})..."
                        )
                        try:
                            time.sleep(2)  # Wait before restart
                            self.start_vision_sensor()
                            logger.info("Vision Sensor restarted successfully")
                            vision_sensor_restart_count = 0  # Reset on success
                        except Exception as e:
                            logger.error(f"Failed to restart Vision Sensor: {e}")
                            if vision_sensor_restart_count >= max_vision_sensor_restarts:
                                logger.error(
                                    "Maximum restart attempts reached for Vision Sensor. "
                                    "Gesture detection will not work."
                                )
                    else:
                        logger.error(
                            "Vision Sensor has crashed too many times. "
                            "Not attempting further restarts."
                        )
                
                # Check Web Dashboard thread
                if self.web_dashboard_thread and not self.web_dashboard_thread.is_alive():
                    logger.error("Web Dashboard thread has died!")
                    
                    if web_dashboard_restart_count < max_web_dashboard_restarts:
                        web_dashboard_restart_count += 1
                        logger.info(
                            f"Attempting to restart Web Dashboard "
                            f"({web_dashboard_restart_count}/{max_web_dashboard_restarts})..."
                        )
                        try:
                            time.sleep(2)  # Wait before restart
                            self.start_web_dashboard()
                            logger.info("Web Dashboard restarted successfully")
                            web_dashboard_restart_count = 0  # Reset on success
                        except Exception as e:
                            logger.error(f"Failed to restart Web Dashboard: {e}")
                            if web_dashboard_restart_count >= max_web_dashboard_restarts:
                                logger.error(
                                    "Maximum restart attempts reached for Web Dashboard. "
                                    "Dashboard will not be accessible."
                                )
                    else:
                        logger.error(
                            "Web Dashboard has crashed too many times. "
                            "Not attempting further restarts."
                        )
                
                # Sleep before next check
                time.sleep(5)
                
            except Exception as e:
                logger.error(f"Error in component monitoring: {e}", exc_info=True)
                time.sleep(5)
    
    def stop(self):
        """Stop all components gracefully."""
        if not self.running:
            return
        
        logger.info("\nStopping PlayAble system...")
        self.running = False
        
        self.cleanup()
    
    def cleanup(self):
        """Clean up all resources with timeout handling."""
        logger.info("Cleaning up resources...")
        cleanup_timeout = 5  # seconds
        
        # Stop Vision Sensor
        if self.vision_sensor:
            try:
                logger.info("Stopping Vision Sensor...")
                self.vision_sensor.stop()
                if self.vision_sensor_thread:
                    self.vision_sensor_thread.join(timeout=cleanup_timeout)
                    if self.vision_sensor_thread.is_alive():
                        logger.warning(
                            f"Vision Sensor thread did not stop within {cleanup_timeout} seconds"
                        )
                    else:
                        logger.info("Vision Sensor stopped")
            except Exception as e:
                logger.error(f"Error stopping Vision Sensor: {e}", exc_info=True)
        
        # Stop Hardware Producer
        if self.hardware_producer_process:
            try:
                logger.info("Stopping Hardware Producer...")
                self.hardware_producer_process.terminate()
                
                # Wait up to cleanup_timeout seconds for graceful shutdown
                try:
                    self.hardware_producer_process.wait(timeout=cleanup_timeout)
                    logger.info("Hardware Producer stopped gracefully")
                except subprocess.TimeoutExpired:
                    logger.warning(
                        f"Hardware Producer did not stop within {cleanup_timeout} seconds, "
                        "forcing kill..."
                    )
                    self.hardware_producer_process.kill()
                    try:
                        self.hardware_producer_process.wait(timeout=2)
                        logger.info("Hardware Producer killed")
                    except subprocess.TimeoutExpired:
                        logger.error("Failed to kill Hardware Producer process")
                    
            except Exception as e:
                logger.error(f"Error stopping Hardware Producer: {e}", exc_info=True)
        
        # Web Dashboard thread will stop automatically (daemon thread)
        if self.web_dashboard_thread:
            logger.info("Waiting for Web Dashboard to stop...")
            self.web_dashboard_thread.join(timeout=cleanup_timeout)
            if self.web_dashboard_thread.is_alive():
                logger.warning(
                    f"Web Dashboard thread did not stop within {cleanup_timeout} seconds"
                )
            else:
                logger.info("Web Dashboard stopped")
        
        # Clean up gesture detector
        if self.gesture_detector:
            try:
                self.gesture_detector.cleanup()
                logger.info("GestureDetector cleaned up")
            except Exception as e:
                logger.error(f"Error cleaning up GestureDetector: {e}", exc_info=True)
        
        logger.info("Cleanup complete")
        logger.info("PlayAble system stopped")
    
    def run(self):
        """Main run loop - start components and monitor."""
        try:
            # Start all components
            self.start()
            
            # Monitor components and keep main thread alive
            self.monitor_components()
            
        except KeyboardInterrupt:
            logger.info("\nReceived keyboard interrupt")
        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
        finally:
            self.stop()


def main():
    """Entry point for PlayAble system."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='PlayAble Rehabilitation Gaming System',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                    # Start with default settings
  python main.py --camera 1         # Use camera at index 1
  python main.py --pipe /tmp/custom # Use custom pipe path

For more information, visit: https://github.com/yourusername/playable
        """
    )
    
    parser.add_argument(
        '--pipe',
        default='/tmp/my_pipe',
        help='Path to Named Pipe (default: /tmp/my_pipe)'
    )
    
    parser.add_argument(
        '--camera',
        type=int,
        default=0,
        help='Camera device index (default: 0)'
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version='PlayAble v1.0.0'
    )
    
    args = parser.parse_args()
    
    # Create and run orchestrator
    orchestrator = PlayAbleOrchestrator(
        pipe_path=args.pipe,
        camera_index=args.camera
    )
    
    orchestrator.run()


if __name__ == '__main__':
    main()
