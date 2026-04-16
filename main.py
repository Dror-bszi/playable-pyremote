#!/usr/bin/env python3
"""
PlayAble Main Orchestrator

Coordinates all system components:
- Hardware Producer (C++ SDL2 subprocess)
- Vision Sensor (Python MediaPipe thread)
- Web Dashboard (Flask thread)
- Named Pipe creation and management
- Network management (WiFi / Hotspot fallback)

This is the single entry point for starting the PlayAble rehabilitation gaming system.
"""

import os
import sys
import select
import struct
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
from network.wifi_manager import WiFiManager, get_hostname


def generate_qr_png():
    """Generate QR code for the dashboard URL and save to web/static/qr.png."""
    try:
        import qrcode  # type: ignore
        hostname = get_hostname()
        url = f'http://{hostname}.local:5000'
        img = qrcode.make(url)
        out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                'web', 'static', 'qr.png')
        img.save(out_path)
        logging.getLogger(__name__).info(f'QR code saved: {url}')
    except Exception as e:
        logging.getLogger(__name__).warning(f'QR code generation failed: {e}')


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


# Rotate logs before opening run.log — run.log = current session, run.log.1 = previous.
# Done here, before setup_logging(), so the logger always starts with an empty file.
_run_log = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'run.log')
if os.path.exists(_run_log):
    import shutil
    shutil.copy2(_run_log, _run_log + '.1')
    open(_run_log, 'w').close()  # truncate; logger will append from a clean start

# Setup logging first, before any other modules
setup_logging()
logger = logging.getLogger(__name__)


class TouchpadReader:
    """Reads touchpad click from the DualSense touchpad evdev device and
    writes TOUCHPAD press/release messages to the named pipe.

    The DualSense's hid-playstation driver exposes the touchpad as a separate
    input node (/dev/input/event7) distinct from the main gamepad device.
    SDL2's GameController API only monitors the main device, so
    SDL_CONTROLLER_BUTTON_TOUCHPAD never fires over BT on this system.
    This thread reads the raw evdev node directly and bypasses SDL2.
    """

    DEVICE = '/dev/input/event7'
    BTN_LEFT = 272   # 0x110 — touchpad physical click reported by hid-playstation
    EV_KEY = 1
    EV_SIZE = 24     # 64-bit: tv_sec(8) + tv_usec(8) + type(2) + code(2) + value(4)
    EV_FMT = 'qqHHi'

    def __init__(self, pipe_path: str = '/tmp/my_pipe'):
        self.pipe_path = pipe_path
        self.running = False
        self.thread: Optional[threading.Thread] = None

    def start(self):
        self.running = True
        self.thread = threading.Thread(
            target=self._read_loop, daemon=True, name='TouchpadReader'
        )
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)

    def _read_loop(self):
        _log = logging.getLogger(__name__)
        try:
            dev_f = open(self.DEVICE, 'rb', buffering=0)
        except FileNotFoundError:
            _log.warning(f"TouchpadReader: {self.DEVICE} not found — touchpad click disabled")
            return
        except PermissionError:
            _log.warning(f"TouchpadReader: no permission to read {self.DEVICE}")
            return

        _log.info(f"TouchpadReader: opened {self.DEVICE}")
        pipe_fd = None
        try:
            while self.running:
                if pipe_fd is None:
                    try:
                        pipe_fd = os.open(self.pipe_path, os.O_WRONLY | os.O_NONBLOCK)
                    except OSError:
                        time.sleep(2)
                        continue

                r, _, _ = select.select([dev_f], [], [], 1.0)
                if not r:
                    continue
                data = dev_f.read(self.EV_SIZE)
                if len(data) < self.EV_SIZE:
                    break
                _, _, typ, code, val = struct.unpack(self.EV_FMT, data)
                if typ == self.EV_KEY and code == self.BTN_LEFT and val in (0, 1):
                    action = 'press' if val == 1 else 'release'
                    msg = f'TOUCHPAD\n{action}\n\n'.encode()
                    try:
                        os.write(pipe_fd, msg)
                    except OSError:
                        try:
                            os.close(pipe_fd)
                        except OSError:
                            pass
                        pipe_fd = None
        finally:
            dev_f.close()
            if pipe_fd is not None:
                try:
                    os.close(pipe_fd)
                except OSError:
                    pass
        _log.info("TouchpadReader stopped")


class PlayAbleOrchestrator:
    """Main orchestrator for the PlayAble rehabilitation gaming system."""

    def __init__(self, pipe_path: str = '/tmp/my_pipe', camera_index: int = 0):
        self.pipe_path = pipe_path
        self.camera_index = camera_index

        # Component references
        self.hardware_producer_process: Optional[subprocess.Popen] = None
        self.touchpad_reader: Optional[TouchpadReader] = None
        self.vision_sensor: Optional[VisionSensor] = None
        self.vision_sensor_thread: Optional[threading.Thread] = None
        self.web_dashboard_thread: Optional[threading.Thread] = None
        self.wifi_manager: Optional[WiFiManager] = None

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

    def check_and_configure_network(self):
        """
        Check WiFi connectivity.  If WiFi is not available within 20s, start the
        PlayAble hotspot so the therapist can configure WiFi via /setup.
        """
        logger.info("\n[0/5] Checking network…")
        self.wifi_manager = WiFiManager()
        if not self.wifi_manager.wait_for_wifi(timeout_seconds=20):
            logger.info("WiFi not available — starting hotspot fallback")
            self.wifi_manager.start_hotspot()
        else:
            ssid = self.wifi_manager.get_current_ssid() or '(unknown)'
            logger.info(f"Network ready: WiFi connected to \"{ssid}\"")

    def create_named_pipe(self):
        """Create Named Pipe if it doesn't exist."""
        try:
            if os.path.exists(self.pipe_path):
                if not os.stat(self.pipe_path).st_mode & 0o010000:
                    logger.warning(f"{self.pipe_path} exists but is not a FIFO, removing...")
                    os.remove(self.pipe_path)
                    os.mkfifo(self.pipe_path)
                else:
                    logger.info(f"Named Pipe already exists: {self.pipe_path}")
            else:
                logger.info(f"Creating Named Pipe: {self.pipe_path}")
                os.mkfifo(self.pipe_path)
            os.chmod(self.pipe_path, 0o666)
            logger.info(f"Named Pipe ready: {self.pipe_path}")
        except Exception as e:
            logger.error(f"Failed to create Named Pipe: {e}")
            raise

    def start_hardware_producer(self):
        """Start Hardware Producer subprocess with validation."""
        try:
            hardware_producer_path = './controller/build/detect_controller'

            if not os.path.exists(hardware_producer_path):
                logger.error(f"Hardware Producer binary not found: {hardware_producer_path}")
                raise FileNotFoundError(f"Hardware Producer binary not found: {hardware_producer_path}")

            if not os.access(hardware_producer_path, os.X_OK):
                logger.info("Attempting to make binary executable...")
                os.chmod(hardware_producer_path, 0o755)

            logger.info("Starting Hardware Producer subprocess...")
            self.hardware_producer_process = subprocess.Popen(
                [hardware_producer_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True
            )
            logger.info(f"Hardware Producer started (PID: {self.hardware_producer_process.pid})")
            time.sleep(1)

            if self.hardware_producer_process.poll() is not None:
                stdout, stderr = self.hardware_producer_process.communicate()
                logger.error("Hardware Producer terminated immediately")
                raise RuntimeError("Hardware Producer failed to start.")

            logger.info("Hardware Producer running successfully")
        except FileNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to start Hardware Producer: {e}", exc_info=True)
            raise

    def initialize_shared_state(self):
        """Initialize shared state objects for gesture detection and mapping."""
        try:
            logger.info("Initializing shared state objects...")
            logger.info("Creating GestureDetector...")
            try:
                self.gesture_detector = GestureDetector(camera_index=self.camera_index)
            except RuntimeError as camera_error:
                logger.error(f"Camera initialization failed: {camera_error}")
                raise
            except ImportError as import_error:
                logger.error(f"Failed to import required modules: {import_error}")
                raise

            logger.info("Creating GestureMapping...")
            try:
                self.gesture_mapping = GestureMapping()
            except Exception as mapping_error:
                logger.error(f"Failed to initialize GestureMapping: {mapping_error}")
                raise

            logger.info("Shared state initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize shared state: {e}", exc_info=True)
            raise

    def start_vision_sensor(self):
        """Start Vision Sensor in dedicated thread."""
        try:
            logger.info("Starting Vision Sensor thread...")
            self.vision_sensor = VisionSensor(
                pipe_path=self.pipe_path,
                camera_index=self.camera_index,
                gesture_detector=self.gesture_detector,
                gesture_mapping=self.gesture_mapping
            )
            self.vision_sensor_thread = threading.Thread(
                target=self._vision_sensor_wrapper,
                name='VisionSensorThread',
                daemon=True
            )
            self.vision_sensor_thread.start()
            time.sleep(1)
            if not self.vision_sensor_thread.is_alive():
                raise RuntimeError("Vision Sensor thread failed to start")
            logger.info("Vision Sensor thread started")
        except Exception as e:
            logger.error(f"Failed to start Vision Sensor: {e}", exc_info=True)
            raise

    def _vision_sensor_wrapper(self):
        try:
            self.vision_sensor.run()
        except Exception as e:
            logger.error(f"Vision Sensor thread exception: {e}", exc_info=True)

    def start_web_dashboard(self):
        """Start Web Dashboard in dedicated thread."""
        try:
            logger.info("Starting Web Dashboard thread...")
            init_app(self.gesture_detector, self.gesture_mapping, self.wifi_manager)
            self.web_dashboard_thread = threading.Thread(
                target=self._web_dashboard_wrapper,
                kwargs={'host': '0.0.0.0', 'port': 5000},
                name='WebDashboardThread',
                daemon=True
            )
            self.web_dashboard_thread.start()
            time.sleep(1)
            if not self.web_dashboard_thread.is_alive():
                raise RuntimeError("Web Dashboard thread failed to start")
            logger.info("Web Dashboard thread started")
            logger.info("Dashboard available at: http://localhost:5000")
        except Exception as e:
            logger.error(f"Failed to start Web Dashboard: {e}", exc_info=True)
            raise

    def _web_dashboard_wrapper(self, host='0.0.0.0', port=5000):
        try:
            run_server(host=host, port=port)
        except Exception as e:
            logger.error(f"Web Dashboard thread exception: {e}", exc_info=True)

    def start(self):
        """Start all system components in the correct order."""
        try:
            logger.info("=" * 60)
            logger.info("Starting PlayAble Rehabilitation Gaming System")
            logger.info("=" * 60)

            generate_qr_png()
            self.check_and_configure_network()

            logger.info("\n[1/5] Creating Named Pipe...")
            self.create_named_pipe()

            logger.info("\n[2/5] Starting Hardware Producer...")
            self.start_hardware_producer()
            self.touchpad_reader = TouchpadReader(pipe_path=self.pipe_path)
            self.touchpad_reader.start()

            logger.info("\n[3/5] Initializing shared state...")
            self.initialize_shared_state()

            logger.info("\n[4/5] Starting Vision Sensor...")
            self.start_vision_sensor()

            logger.info("\n[5/5] Starting Web Dashboard...")
            self.start_web_dashboard()

            self.running = True

            logger.info("\n" + "=" * 60)
            logger.info("PlayAble System Started Successfully!")
            logger.info("=" * 60)
            logger.info("\nSystem Status:")
            logger.info(f"  - Hardware Producer: Running (PID {self.hardware_producer_process.pid})")
            logger.info(f"  - Vision Sensor:     Running")
            logger.info(f"  - Web Dashboard:     Running (http://localhost:5000)")
            logger.info(f"  - Named Pipe:        {self.pipe_path}")
            if self.wifi_manager:
                net = self.wifi_manager.get_status()
                logger.info(f"  - Network:           {net['mode'].upper()} — {net.get('ssid') or ''}")
            logger.info("\nPress Ctrl+C to stop the system")
            logger.info("=" * 60 + "\n")

        except Exception as e:
            logger.error(f"Failed to start PlayAble system: {e}")
            self.cleanup()
            raise

    def monitor_components(self):
        """Monitor component health and restart if necessary."""
        hardware_producer_restart_count = 0
        max_hardware_producer_restarts = 3
        vision_sensor_restart_count = 0
        max_vision_sensor_restarts = 3
        web_dashboard_restart_count = 0
        max_web_dashboard_restarts = 3

        while self.running:
            try:
                if self.hardware_producer_process:
                    if self.hardware_producer_process.poll() is not None:
                        logger.error("Hardware Producer has crashed!")
                        if hardware_producer_restart_count < max_hardware_producer_restarts:
                            hardware_producer_restart_count += 1
                            logger.info(f"Attempting to restart Hardware Producer ({hardware_producer_restart_count}/{max_hardware_producer_restarts})...")
                            try:
                                time.sleep(2)
                                self.start_hardware_producer()
                                logger.info("Hardware Producer restarted successfully")
                                hardware_producer_restart_count = 0
                            except Exception as e:
                                logger.error(f"Failed to restart Hardware Producer: {e}")
                        else:
                            logger.error("Maximum restart attempts reached for Hardware Producer.")

                if self.vision_sensor_thread and not self.vision_sensor_thread.is_alive():
                    logger.error("Vision Sensor thread has died!")
                    if vision_sensor_restart_count < max_vision_sensor_restarts:
                        vision_sensor_restart_count += 1
                        logger.info(f"Attempting to restart Vision Sensor ({vision_sensor_restart_count}/{max_vision_sensor_restarts})...")
                        try:
                            time.sleep(2)
                            self.start_vision_sensor()
                            logger.info("Vision Sensor restarted successfully")
                            vision_sensor_restart_count = 0
                        except Exception as e:
                            logger.error(f"Failed to restart Vision Sensor: {e}")
                    else:
                        logger.error("Maximum restart attempts reached for Vision Sensor.")

                if self.web_dashboard_thread and not self.web_dashboard_thread.is_alive():
                    logger.error("Web Dashboard thread has died!")
                    if web_dashboard_restart_count < max_web_dashboard_restarts:
                        web_dashboard_restart_count += 1
                        logger.info(f"Attempting to restart Web Dashboard ({web_dashboard_restart_count}/{max_web_dashboard_restarts})...")
                        try:
                            time.sleep(2)
                            self.start_web_dashboard()
                            logger.info("Web Dashboard restarted successfully")
                            web_dashboard_restart_count = 0
                        except Exception as e:
                            logger.error(f"Failed to restart Web Dashboard: {e}")
                    else:
                        logger.error("Maximum restart attempts reached for Web Dashboard.")

                time.sleep(5)

            except Exception as e:
                logger.error(f"Error in component monitoring: {e}", exc_info=True)
                time.sleep(5)

    def stop(self):
        if not self.running:
            return
        logger.info("\nStopping PlayAble system...")
        self.running = False
        self.cleanup()

    def cleanup(self):
        """Clean up all resources."""
        logger.info("Cleaning up resources...")
        cleanup_timeout = 5

        # Stop Vision Sensor
        if self.vision_sensor:
            try:
                logger.info("Stopping Vision Sensor...")
                self.vision_sensor.stop()
                if self.vision_sensor_thread:
                    self.vision_sensor_thread.join(timeout=cleanup_timeout)
                    if not self.vision_sensor_thread.is_alive():
                        logger.info("Vision Sensor stopped")
            except Exception as e:
                logger.error(f"Error stopping Vision Sensor: {e}", exc_info=True)

        # Stop Touchpad Reader
        if self.touchpad_reader:
            self.touchpad_reader.stop()

        # Stop Hardware Producer
        if self.hardware_producer_process:
            try:
                logger.info("Stopping Hardware Producer...")
                self.hardware_producer_process.terminate()
                try:
                    self.hardware_producer_process.wait(timeout=cleanup_timeout)
                    logger.info("Hardware Producer stopped gracefully")
                except subprocess.TimeoutExpired:
                    logger.warning("Hardware Producer did not stop in time, killing...")
                    self.hardware_producer_process.kill()
                    self.hardware_producer_process.wait(timeout=2)
            except Exception as e:
                logger.error(f"Error stopping Hardware Producer: {e}", exc_info=True)

        # Stop hotspot if active
        if self.wifi_manager:
            try:
                self.wifi_manager.stop_hotspot()
            except Exception as e:
                logger.error(f"Error stopping hotspot: {e}")

        # Web Dashboard thread will stop automatically (daemon thread)
        if self.web_dashboard_thread:
            logger.info("Waiting for Web Dashboard to stop...")
            self.web_dashboard_thread.join(timeout=cleanup_timeout)

        # Clean up gesture detector
        if self.gesture_detector:
            try:
                self.gesture_detector.cleanup()
                logger.info("GestureDetector cleaned up")
            except ValueError:
                pass
            except Exception as e:
                logger.error(f"Error cleaning up GestureDetector: {e}", exc_info=True)

        logger.info("Cleanup complete")
        logger.info("PlayAble system stopped")

    def run(self):
        """Main run loop - start components and monitor."""
        try:
            self.start()
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

    parser = argparse.ArgumentParser(description='PlayAble Rehabilitation Gaming System')
    parser.add_argument('--pipe', default='/tmp/my_pipe', help='Path to Named Pipe')
    parser.add_argument('--camera', type=int, default=0, help='Camera device index')
    parser.add_argument('--version', action='version', version='PlayAble v1.0.0')
    args = parser.parse_args()

    orchestrator = PlayAbleOrchestrator(
        pipe_path=args.pipe,
        camera_index=args.camera
    )
    orchestrator.run()


if __name__ == '__main__':
    main()
