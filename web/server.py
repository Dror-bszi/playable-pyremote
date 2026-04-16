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
import re
import json
import logging
import subprocess
import asyncio
import threading
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from flask import Flask, render_template, request, jsonify, Response
from flask_cors import CORS
import cv2

# Import core components
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.gestures import GestureDetector
from core.mappings import GestureMapping
from pyremoteplay.device import RPDevice
from pyremoteplay.pipe_reader import PipeReader

# Configure logging (if not already configured by main)
if not logging.getLogger().handlers:
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
bluetooth_manager: Optional['BluetoothManager'] = None

# ANSI escape code stripper
_ANSI_ESCAPE = re.compile(r'\x1b\[[0-9;]*m')

PS5_CONFIG_PATH = 'config/ps5_config.json'


def _check_tokens_valid() -> bool:
    """Return True if stored PSN tokens have a usable online_id."""
    if not psn_connection_manager or not psn_connection_manager.tokens:
        return False
    return bool(psn_connection_manager.tokens.get('online_id'))


def _load_ps5_config() -> dict:
    """Load saved PS5 host config."""
    try:
        if os.path.exists(PS5_CONFIG_PATH):
            with open(PS5_CONFIG_PATH) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_ps5_config(data: dict):
    """Save PS5 host config."""
    try:
        os.makedirs(os.path.dirname(PS5_CONFIG_PATH), exist_ok=True)
        with open(PS5_CONFIG_PATH, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        logger.warning(f"Could not save PS5 config: {e}")


class PSNConnectionManager:
    """Manages PSN authentication and Remote Play connection lifecycle."""

    def __init__(self, config_file='config/psn_tokens.json'):
        self.config_file = config_file
        self.tokens = self._load_tokens()
        self.device: Optional[RPDevice] = None
        self._session_loop: Optional[asyncio.AbstractEventLoop] = None
        self._session_thread: Optional[threading.Thread] = None
        self._pipe_reader = None
        self.is_authenticated = self.tokens is not None
        self.is_connected = False
        self._lock = threading.Lock()

        logger.info("PSNConnectionManager initialized")

    def _load_tokens(self) -> Optional[Dict[str, str]]:
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load PSN tokens: {e}")
        return None

    def _save_tokens(self, tokens: Dict[str, str]):
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
        try:
            from pyremoteplay.oauth import get_login_url
            auth_url = get_login_url()
            logger.info("OAuth flow started")
            return auth_url
        except Exception as e:
            logger.error(f"Failed to start OAuth flow: {e}")
            raise

    def handle_redirect(self, redirect_url: str) -> Dict[str, str]:
        try:
            from pyremoteplay.oauth import get_user_account
            account_info = get_user_account(redirect_url)
            if account_info is None:
                raise ValueError("Failed to get user account from redirect URL")
            self._save_tokens(account_info)
            logger.info("OAuth tokens obtained successfully")
            return account_info
        except Exception as e:
            logger.error(f"Failed to handle OAuth redirect: {e}")
            raise

    def register_device(self, pin: str, ps5_host: str = None) -> bool:
        try:
            from pyremoteplay.register import register
            from pyremoteplay.device import RPDevice
            from pyremoteplay.profile import Profiles
            from pyremoteplay.profile import format_user_account
            from pyremoteplay.util import add_regist_data

            if not self.tokens:
                raise ValueError("No authentication tokens available")

            psn_id = self.tokens.get('user_rpid')
            if not psn_id:
                raise ValueError("PSN ID (user_rpid) not found in tokens")

            if not ps5_host:
                raise ValueError("PS5 host address is required for registration")

            device = RPDevice(ps5_host)
            status = device.get_status()
            if not status or status.get('status-code') != 200:
                raise ValueError(f"Could not reach PS5 at {ps5_host}")

            regist_data = register(ps5_host, psn_id, pin)
            if not regist_data:
                raise ValueError("Registration failed - invalid PIN or device unreachable")

            profiles = Profiles.load()
            user_profile = None
            user_name = self.tokens.get('online_id')
            if user_name and profiles:
                user_profile = profiles.get_user_profile(user_name)

            if not user_profile:
                user_profile = format_user_account(self.tokens)
                if not user_profile:
                    raise ValueError("Failed to create user profile from tokens")
                logger.info(f"Created new user profile: {user_profile.name}")
            else:
                logger.info(f"Using existing user profile: {user_profile.name}")

            if "hosts" not in user_profile.data:
                user_profile.data["hosts"] = {}

            add_regist_data(user_profile.data, status, regist_data)
            profiles.update_user(user_profile)
            profiles.save()

            # Save PS5 host for future use
            _save_ps5_config({'last_host': ps5_host})

            logger.info(f"Device registered successfully: {user_profile.name}")
            return True
        except Exception as e:
            logger.error(f"Failed to register device: {e}")
            raise

    def start_remoteplay(self, ps5_host: str = None) -> bool:
        """Start a persistent headless Remote Play session using pyremoteplay as a library."""
        with self._lock:
            if self.device and self.device.connected:
                logger.warning("Remote Play already running")
                return False

            try:
                if not self.tokens:
                    raise ValueError("No authentication tokens available. Please authenticate first.")
                if not ps5_host:
                    raise ValueError("ps5_host is required")

                user = self.tokens.get("online_id")
                if not user:
                    raise ValueError("No online_id in tokens")

                # Connect to device and fetch status (needed for mac_address / profile lookup)
                device = RPDevice(ps5_host)
                status = device.get_status()
                if not status:
                    raise RuntimeError(f"Could not reach PS5 at {ps5_host}")
                if status.get("status-code") != 200:
                    raise RuntimeError(f"PS5 is not ready (status-code: {status.get('status-code')})")

                # Verify user is registered with this device
                registered_users = device.get_users()
                if user not in registered_users:
                    raise RuntimeError(
                        f"User '{user}' is not registered with PS5 at {ps5_host}. "
                        "Complete device registration first."
                    )

                # Create session — no AV receiver, controller input only
                loop = asyncio.new_event_loop()
                device.create_session(user, loop=loop)
                ready_event = threading.Event()

                async def _connect():
                    started = await device.connect()
                    if not started:
                        ready_event.set()
                        return
                    await device.async_wait_for_session()
                    ready_event.set()

                def _run_session():
                    try:
                        loop.run_until_complete(loop.create_task(_connect()))
                        if device.session and device.session.is_ready:
                            device.controller.start()
                            pipe_reader = PipeReader(device.controller)
                            pipe_reader.start()
                            self._pipe_reader = pipe_reader
                            logger.info("PipeReader started — pipe writers will now unblock")
                        loop.run_forever()
                    except Exception as exc:
                        logger.error(f"Session thread error: {exc}", exc_info=True)
                    finally:
                        logger.info("Remote Play session thread ended")

                self._session_thread = threading.Thread(
                    target=_run_session,
                    name="RemotePlayThread",
                    daemon=True,
                )
                self._session_thread.start()

                # Block up to 10 s for session to reach READY
                ready_event.wait(timeout=10)

                if device.session and device.session.is_ready:
                    self.device = device
                    self._session_loop = loop
                    self.is_connected = True
                    logger.info(f"Remote Play session READY (PS5: {ps5_host}, user: {user})")
                    return True

                # Did not become ready — clean up
                loop.call_soon_threadsafe(loop.stop)
                error = device.session.error if device.session else "unknown error"
                raise RuntimeError(f"Remote Play session failed to reach READY state: {error}")

            except ValueError as ve:
                logger.error(f"Configuration error: {ve}")
                self.is_connected = False
                raise
            except Exception as e:
                logger.error(f"Failed to start Remote Play: {e}", exc_info=True)
                self.is_connected = False
                raise

    def stop_remoteplay(self) -> bool:
        """Stop the Remote Play session gracefully."""
        with self._lock:
            if not self.device and not self._session_loop:
                logger.warning("No Remote Play session to stop")
                return False

            try:
                if self._pipe_reader:
                    self._pipe_reader.stop()
                    self._pipe_reader = None

                if self.device:
                    self.device.disconnect()
                    self.device = None

                if self._session_loop:
                    self._session_loop.call_soon_threadsafe(self._session_loop.stop)
                    self._session_loop = None

                self.is_connected = False
                logger.info("Remote Play stopped")
                return True

            except Exception as e:
                logger.error(f"Failed to stop Remote Play: {e}")
                raise

    def get_status(self) -> Dict[str, Any]:
        if self.device:
            if not self.device.connected:
                self.is_connected = False
                self.device = None

        return {
            'authenticated': self.is_authenticated,
            'connected': self.is_connected,
            'process_running': self.device is not None,
        }


class BluetoothManager:
    """Manages Bluetooth scanning and pairing via bluetoothctl."""

    def __init__(self):
        self._scan_process: Optional[subprocess.Popen] = None
        self._discovered: Dict[str, str] = {}   # mac -> name
        self._scanning = False
        self._lock = threading.Lock()

    def start_scan(self) -> dict:
        with self._lock:
            if self._scanning:
                return {'already_scanning': True}
            self._scanning = True
            self._discovered = {}

        thread = threading.Thread(target=self._scan_worker, daemon=True, name="BTScanThread")
        thread.start()
        return {'started': True}

    def _scan_worker(self):
        try:
            subprocess.run(['bluetoothctl', 'power', 'on'], timeout=3, capture_output=True)
            self._scan_process = subprocess.Popen(
                ['bluetoothctl', 'scan', 'on'],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            start = time.time()
            while self._scanning and (time.time() - start) < 15:
                line = self._scan_process.stdout.readline()
                if not line:
                    break
                clean = _ANSI_ESCAPE.sub('', line).strip()
                # [NEW] Device XX:XX:XX:XX:XX:XX Device Name
                m = re.match(r'\[NEW\]\s+Device\s+([0-9A-Fa-f:]{17})\s+(.*)', clean)
                if m:
                    mac = m.group(1)
                    name = m.group(2).strip()
                    # Skip entries where name is just the MAC with dashes
                    if name and re.match(r'^[0-9A-Fa-f-]{17}$', name):
                        name = None
                    if name:
                        with self._lock:
                            self._discovered[mac] = name
                        logger.info(f"BT scan found: {name} ({mac})")
        except Exception as e:
            logger.error(f"BT scan worker error: {e}")
        finally:
            self._stop_scan_process()
            with self._lock:
                self._scanning = False
            logger.info("BT scan ended")

    def _stop_scan_process(self):
        if self._scan_process:
            try:
                self._scan_process.terminate()
            except Exception:
                pass
            self._scan_process = None
        try:
            subprocess.run(['bluetoothctl', 'scan', 'off'], timeout=3, capture_output=True)
        except Exception:
            pass

    def stop_scan(self):
        with self._lock:
            self._scanning = False
        self._stop_scan_process()

    def get_results(self) -> dict:
        with self._lock:
            return {
                'scanning': self._scanning,
                'devices': [
                    {'mac': mac, 'name': name}
                    for mac, name in self._discovered.items()
                ],
            }

    def pair_device(self, mac: str) -> dict:
        """Pair, trust, and connect a device. Stops any active scan first."""
        self.stop_scan()
        results = {}
        for action in ['pair', 'trust', 'connect']:
            try:
                r = subprocess.run(
                    ['bluetoothctl', action, mac],
                    capture_output=True, text=True, timeout=20,
                )
                results[action] = r.returncode == 0
                logger.info(f"bluetoothctl {action} {mac}: rc={r.returncode}")
            except subprocess.TimeoutExpired:
                results[action] = False
                logger.warning(f"bluetoothctl {action} {mac}: timed out")
            except Exception as e:
                results[action] = False
                logger.error(f"bluetoothctl {action} {mac}: {e}")
        return results


def init_app(detector: GestureDetector, mapping: GestureMapping):
    """Initialize Flask app with shared state objects. Called by main orchestrator."""
    global gesture_detector, gesture_mapping, psn_connection_manager, bluetooth_manager

    gesture_detector = detector
    gesture_mapping = mapping
    psn_connection_manager = PSNConnectionManager()
    bluetooth_manager = BluetoothManager()

    logger.info("Flask app initialized with shared state")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/')
def dashboard():
    return render_template('dashboard.html')



@app.route('/api/system/restart', methods=['POST'])
def system_restart():
    """Kill and relaunch main.py cleanly via a detached background shell."""
    try:
        import sys
        # Resolve paths once so the relaunch shell needs no assumptions
        python  = sys.executable
        main_py = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'main.py')
        run_log = os.path.join(os.path.dirname(main_py), 'run.log')

        # Write a restart script to disk — avoids all shell quoting issues
        # and gives us a reliable relaunch even when fds are /dev/null.
        # sleep 9 > old shutdown (5s dashboard timeout + margin) so port 5000
        # and camera are fully released before the new process starts.
        restart_sh = os.path.join(os.path.dirname(main_py), '_restart.sh')
        with open(restart_sh, 'w') as _f:
            _f.write(
                f"#!/bin/bash\n"
                f"sleep 1\n"
                f"pkill -f 'python.*main.py' 2>/dev/null\n"
                f"sleep 9\n"
                f"cd {os.path.dirname(main_py)}\n"
                f"{python} {main_py} >> {run_log} 2>&1\n"
            )
        os.chmod(restart_sh, 0o755)
        subprocess.Popen([restart_sh],
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL,
                         start_new_session=True)
        logger.info("System restart initiated")
        return jsonify({'success': True, 'message': 'Restarting...'})
    except Exception as e:
        logger.error(f"Restart error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/status')
def get_status():
    try:
        status = {
            'controller_connected': False,
            'controller_name': None,
            'ps5_connected': False,
            'camera_active': False,
            'active_mappings': {},
            'psn_authenticated': False,
            'fps': 0.0,
        }

        if psn_connection_manager:
            psn_status = psn_connection_manager.get_status()
            status['psn_authenticated'] = psn_status['authenticated']
            status['ps5_connected'] = psn_status['connected']

        if gesture_detector:
            status['camera_active'] = gesture_detector.is_active()
            status['fps'] = gesture_detector.get_fps()

        if gesture_mapping:
            status['active_mappings'] = gesture_mapping.get_active_mappings()

        # Real controller detection — check /proc first (USB), fall back to bluetoothctl (BT)
        try:
            proc = subprocess.run(
                ['cat', '/proc/bus/input/devices'],
                capture_output=True, text=True, timeout=2,
            )
            for block in proc.stdout.split('\n\n'):
                if 'DualSense' in block or ('Sony' in block and 'Wireless Controller' in block):
                    m = re.search(r'N: Name="([^"]+)"', block)
                    if m:
                        name = m.group(1)
                        if 'Motion' not in name and 'Touchpad' not in name:
                            status['controller_connected'] = True
                            status['controller_name'] = name
                            break
        except Exception:
            pass

        # BT fallback: if not found via /proc, query bluetoothctl
        if not status['controller_connected']:
            bt_conn, bt_name = _bt_dualsense_connected()
            if bt_conn:
                status['controller_connected'] = True
                status['controller_name'] = bt_name

        return jsonify(status)
    except Exception as e:
        logger.error(f"Status endpoint error: {e}")
        return jsonify({'error': str(e)}), 500


# ── PS5 Devices ──────────────────────────────────────────────────────────────

@app.route('/api/ps5/devices')
def get_ps5_devices():
    """Return saved PS5 devices from pyremoteplay profile."""
    try:
        from pyremoteplay.profile import Profiles

        devices = []
        if psn_connection_manager and psn_connection_manager.tokens:
            user = psn_connection_manager.tokens.get('online_id')
            try:
                profiles = Profiles.load()
                if profiles and user:
                    profile = profiles.get_user_profile(user)
                    if profile and 'hosts' in profile.data:
                        for mac, host_info in profile.data['hosts'].items():
                            data = host_info.get('data', {})
                            # Format MAC as XX:XX:XX:XX:XX:XX
                            fmt_mac = ':'.join(mac[i:i+2] for i in range(0, 12, 2)).upper() if len(mac) == 12 else mac
                            devices.append({
                                'mac': fmt_mac,
                                'nickname': data.get('Nickname', data.get('AP-Name', 'PS5')),
                                'type': host_info.get('type', 'PS5'),
                            })
            except Exception as e:
                logger.warning(f"Could not load profiles: {e}")

        ps5_config = _load_ps5_config()

        username = None
        if psn_connection_manager and psn_connection_manager.tokens:
            username = psn_connection_manager.tokens.get('online_id')

        return jsonify({
            'devices': devices,
            'last_host': ps5_config.get('last_host'),
            'has_credentials': _check_tokens_valid(),
            'authenticated': psn_connection_manager.is_authenticated if psn_connection_manager else False,
            'username': username,
        })
    except Exception as e:
        logger.error(f"Get PS5 devices error: {e}")
        return jsonify({'error': str(e)}), 500


# ── Controller ───────────────────────────────────────────────────────────────

@app.route('/api/controller/status')
def get_controller_status():
    """Get real DualSense connection status from OS input devices."""
    try:
        proc = subprocess.run(
            ['cat', '/proc/bus/input/devices'],
            capture_output=True, text=True, timeout=2,
        )
        for block in proc.stdout.split('\n\n'):
            if 'DualSense' in block or ('Sony' in block and 'Wireless Controller' in block):
                m = re.search(r'N: Name="([^"]+)"', block)
                if m:
                    name = m.group(1)
                    if 'Motion' not in name and 'Touchpad' not in name:
                        return jsonify({'connected': True, 'name': name})
    except Exception as e:
        logger.error(f"Controller status error: {e}")

    # BT fallback
    bt_conn, bt_name = _bt_dualsense_connected()
    if bt_conn:
        return jsonify({'connected': True, 'name': bt_name})
    return jsonify({'connected': False, 'name': None})


# ── Bluetooth ────────────────────────────────────────────────────────────────

@app.route('/api/bluetooth/scan/start', methods=['POST'])
def bluetooth_scan_start():
    if not bluetooth_manager:
        return jsonify({'error': 'Bluetooth manager not initialized'}), 500
    result = bluetooth_manager.start_scan()
    return jsonify(result)


@app.route('/api/bluetooth/scan/stop', methods=['POST'])
def bluetooth_scan_stop():
    if not bluetooth_manager:
        return jsonify({'error': 'Bluetooth manager not initialized'}), 500
    bluetooth_manager.stop_scan()
    return jsonify({'stopped': True})


@app.route('/api/bluetooth/scan/results')
def bluetooth_scan_results():
    if not bluetooth_manager:
        return jsonify({'error': 'Bluetooth manager not initialized'}), 500
    return jsonify(bluetooth_manager.get_results())


@app.route('/api/bluetooth/pair', methods=['POST'])
def bluetooth_pair():
    if not bluetooth_manager:
        return jsonify({'error': 'Bluetooth manager not initialized'}), 500
    data = request.get_json() or {}
    mac = data.get('mac', '').strip()
    if not mac:
        return jsonify({'error': 'mac is required'}), 400
    if not re.match(r'^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$', mac):
        return jsonify({'error': f'Invalid MAC address: {mac}'}), 400
    results = bluetooth_manager.pair_device(mac)
    success = results.get('pair') and results.get('trust')
    return jsonify({'success': success, 'results': results})


@app.route('/api/bluetooth/paired')
def bluetooth_paired():
    """Return paired DualSense controllers with per-device connection status."""
    try:
        result = subprocess.run(
            ['bluetoothctl', 'devices'],
            capture_output=True, text=True, timeout=5,
        )
        devices = []
        for line in result.stdout.splitlines():
            clean = _ANSI_ESCAPE.sub('', line).strip()
            m = re.match(r'Device\s+([0-9A-Fa-f:]{17})\s+(.*)', clean)
            if m:
                mac, name = m.group(1), m.group(2).strip()
                if 'DualSense' in name or 'Wireless Controller' in name:
                    info = subprocess.run(
                        ['bluetoothctl', 'info', mac],
                        capture_output=True, text=True, timeout=3,
                    )
                    connected = 'Connected: yes' in info.stdout
                    devices.append({'mac': mac, 'name': name, 'connected': connected})
        return jsonify({'devices': devices})
    except Exception as e:
        logger.error(f"Bluetooth paired error: {e}")
        return jsonify({'devices': [], 'error': str(e)})


@app.route('/api/bluetooth/connect', methods=['POST'])
def bluetooth_connect():
    """Connect to an already-paired Bluetooth device."""
    data = request.get_json() or {}
    mac = data.get('mac', '').strip()
    if not mac or not re.match(r'^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$', mac):
        return jsonify({'error': 'Invalid MAC address'}), 400
    try:
        r = subprocess.run(
            ['bluetoothctl', 'connect', mac],
            capture_output=True, text=True, timeout=15,
        )
        success = r.returncode == 0
        logger.info(f"bluetoothctl connect {mac}: rc={r.returncode}")
        return jsonify({'success': success})
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'Connection timed out'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})



def _bt_dualsense_connected():
    """Return (connected, name) for the first BT-connected DualSense/Wireless Controller."""
    try:
        r = subprocess.run(['bluetoothctl', 'devices'], capture_output=True, text=True, timeout=5)
        for line in r.stdout.splitlines():
            clean = _ANSI_ESCAPE.sub('', line).strip()
            m = re.match(r'Device\s+([0-9A-Fa-f:]{17})\s+(.*)', clean)
            if m:
                mac, name = m.group(1), m.group(2).strip()
                if 'DualSense' in name or 'Wireless Controller' in name:
                    info = subprocess.run(
                        ['bluetoothctl', 'info', mac],
                        capture_output=True, text=True, timeout=3,
                    )
                    if 'Connected: yes' in info.stdout:
                        return True, name
    except Exception:
        pass
    return False, None


# ── PSN Auth ─────────────────────────────────────────────────────────────────

@app.route('/api/psn/login', methods=['POST'])
def psn_login():
    try:
        if not psn_connection_manager:
            return jsonify({'error': 'PSN connection manager not initialized'}), 500
        auth_url = psn_connection_manager.start_oauth_flow()
        return jsonify({'success': True, 'authorization_url': auth_url})
    except Exception as e:
        logger.error(f"PSN login error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/psn/callback', methods=['POST'])
def psn_callback():
    try:
        if not psn_connection_manager:
            return jsonify({'error': 'PSN connection manager not initialized'}), 500
        data = request.get_json()
        redirect_url = data.get('redirect_url')
        if not redirect_url:
            return jsonify({'error': 'redirect_url is required'}), 400
        psn_connection_manager.handle_redirect(redirect_url)
        return jsonify({'success': True, 'message': 'Authentication successful', 'authenticated': True})
    except Exception as e:
        logger.error(f"PSN callback error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/psn/pin', methods=['POST'])
def submit_pin():
    try:
        if not psn_connection_manager:
            return jsonify({'error': 'PSN connection manager not initialized'}), 500
        data = request.get_json()
        pin = data.get('pin')
        ps5_host = data.get('ps5_host')
        if not pin:
            return jsonify({'error': 'pin is required'}), 400
        success = psn_connection_manager.register_device(pin, ps5_host=ps5_host)
        return jsonify({'success': success, 'message': 'Device registered successfully'})
    except Exception as e:
        logger.error(f"PIN submission error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/remoteplay/connect', methods=['POST'])
def connect_remoteplay():
    try:
        if not psn_connection_manager:
            return jsonify({'error': 'PSN connection manager not initialized'}), 500
        data = request.get_json() or {}
        ps5_host = data.get('ps5_host')
        success = psn_connection_manager.start_remoteplay(ps5_host)
        return jsonify({'success': success, 'message': 'Remote Play started', 'connected': True})
    except Exception as e:
        logger.error(f"Remote Play connect error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/remoteplay/disconnect', methods=['POST'])
def disconnect_remoteplay():
    try:
        if not psn_connection_manager:
            return jsonify({'error': 'PSN connection manager not initialized'}), 500
        success = psn_connection_manager.stop_remoteplay()
        return jsonify({'success': success, 'message': 'Remote Play stopped', 'connected': False})
    except Exception as e:
        logger.error(f"Remote Play disconnect error: {e}")
        return jsonify({'error': str(e)}), 500


# ── Thresholds ───────────────────────────────────────────────────────────────

@app.route('/api/thresholds', methods=['GET', 'POST'])
def thresholds():
    if request.method == 'GET':
        try:
            if not gesture_detector:
                return jsonify({'error': 'Gesture detector not initialized'}), 500
            return jsonify(gesture_detector.get_thresholds())
        except Exception as e:
            logger.error(f"Get thresholds error: {e}")
            return jsonify({'error': str(e)}), 500
    else:
        try:
            if not gesture_detector:
                return jsonify({'error': 'Gesture detector not initialized'}), 500
            data = request.get_json()
            delta_threshold = data.get('delta_threshold')
            raise_minimum = data.get('raise_minimum')
            shrug_minimum = data.get('shrug_minimum')
            mouth_open_minimum = data.get('mouth_open_minimum')
            if delta_threshold is None or raise_minimum is None:
                return jsonify({'error': 'delta_threshold and raise_minimum are required'}), 400
            if not (0.01 <= delta_threshold <= 0.20):
                return jsonify({'error': 'delta_threshold must be between 0.01 and 0.20'}), 400
            if not (0.05 <= raise_minimum <= 0.50):
                return jsonify({'error': 'raise_minimum must be between 0.05 and 0.50'}), 400
            if shrug_minimum is not None and not (0.01 <= shrug_minimum <= 0.50):
                return jsonify({'error': 'shrug_minimum must be between 0.01 and 0.50'}), 400
            if mouth_open_minimum is not None and not (0.10 <= mouth_open_minimum <= 1.0):
                return jsonify({'error': 'mouth_open_minimum must be between 0.10 and 1.0'}), 400
            # Update live GestureDetector in memory immediately
            gesture_detector.update_thresholds(delta_threshold, raise_minimum,
                                                shrug_minimum, mouth_open_minimum)
            # Also persist to mappings.json so vision sensor picks up via live reload
            if gesture_mapping:
                gesture_mapping.update_thresholds(delta_threshold, raise_minimum,
                                                  shrug_minimum, mouth_open_minimum)
            updated = gesture_detector.get_thresholds()
            return jsonify({
                'success': True,
                'message': 'Thresholds updated',
                'thresholds': updated,
            })
        except Exception as e:
            logger.error(f"Update thresholds error: {e}")
            return jsonify({'error': str(e)}), 500


# ── Mappings ─────────────────────────────────────────────────────────────────

@app.route('/api/mappings', methods=['GET', 'POST', 'DELETE'])
def mappings():
    if request.method == 'GET':
        try:
            if not gesture_mapping:
                return jsonify({'error': 'Gesture mapping not initialized'}), 500
            return jsonify(gesture_mapping.get_active_mappings())
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
            valid_buttons = ['CROSS', 'CIRCLE', 'SQUARE', 'TRIANGLE', 'R1', 'R2', 'L1', 'L2']
            if button not in valid_buttons:
                return jsonify({'error': f'button must be one of {valid_buttons}'}), 400
            gesture_mapping.add_mapping(gesture_name, button)
            return jsonify({'success': True, 'message': 'Mapping added',
                            'mapping': {'gesture_name': gesture_name, 'button': button}})
        except Exception as e:
            logger.error(f"Add mapping error: {e}")
            return jsonify({'error': str(e)}), 500

    else:
        try:
            if not gesture_mapping:
                return jsonify({'error': 'Gesture mapping not initialized'}), 500
            data = request.get_json()
            gesture_name = data.get('gesture_name')
            if not gesture_name:
                return jsonify({'error': 'gesture_name is required'}), 400
            gesture_mapping.remove_mapping(gesture_name)
            return jsonify({'success': True, 'message': 'Mapping removed', 'gesture_name': gesture_name})
        except Exception as e:
            logger.error(f"Remove mapping error: {e}")
            return jsonify({'error': str(e)}), 500


# ── Video Feed ───────────────────────────────────────────────────────────────

@app.route('/video_feed')
def video_feed():
    def generate_frames():
        consecutive_errors = 0
        max_consecutive_errors = 10

        while True:
            try:
                if not gesture_detector:
                    import numpy as np
                    blank = cv2.imencode('.jpg', np.zeros((480, 640, 3), dtype='uint8'))[1].tobytes()
                    yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + blank + b'\r\n')
                    time.sleep(0.1)
                    consecutive_errors = 0
                    continue

                if not gesture_detector.is_active():
                    import numpy as np
                    error_frame = np.zeros((480, 640, 3), dtype='uint8')
                    cv2.putText(error_frame, "Camera Not Available", (150, 240),
                                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                    error_bytes = cv2.imencode('.jpg', error_frame)[1].tobytes()
                    yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + error_bytes + b'\r\n')
                    time.sleep(0.5)
                    consecutive_errors += 1
                    if consecutive_errors >= max_consecutive_errors:
                        break
                    continue

                frame = gesture_detector.get_current_frame()
                if frame is None:
                    if consecutive_errors == 0:
                        logger.warning("get_current_frame() returned None - camera may not be initialized or accessible")
                    import numpy as np
                    error_frame = np.zeros((480, 640, 3), dtype='uint8')
                    cv2.putText(error_frame, "No Frame Available", (150, 220),
                                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                    cv2.putText(error_frame, "Check camera connection", (100, 260),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                    blank = cv2.imencode('.jpg', error_frame)[1].tobytes()
                    yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + blank + b'\r\n')
                    time.sleep(0.1)
                    consecutive_errors += 1
                    if consecutive_errors >= max_consecutive_errors:
                        logger.error("Failed to get camera frames for extended period - check camera initialization")
                        break
                    continue

                ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                if not ret:
                    consecutive_errors += 1
                    continue

                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
                consecutive_errors = 0
                time.sleep(0.066)

            except cv2.error as cv_error:
                logger.error(f"OpenCV error in video feed: {cv_error}")
                consecutive_errors += 1
                time.sleep(0.1)
                if consecutive_errors >= max_consecutive_errors:
                    break
            except Exception as e:
                logger.error(f"Video feed error: {e}", exc_info=True)
                consecutive_errors += 1
                time.sleep(0.1)
                if consecutive_errors >= max_consecutive_errors:
                    break

    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


def run_server(host='0.0.0.0', port=5000):
    max_port_attempts = 5
    current_port = port
    for attempt in range(max_port_attempts):
        try:
            logger.info(f"Starting Flask server on {host}:{current_port}")
            app.run(host=host, port=current_port, debug=False, threaded=True)
            return
        except OSError as e:
            if 'Address already in use' in str(e) or 'Errno 48' in str(e):
                logger.warning(f"Port {current_port} already in use")
                if attempt < max_port_attempts - 1:
                    current_port += 1
                else:
                    raise RuntimeError(f"Could not start web server - ports {port} to {current_port} are in use.")
            else:
                logger.error(f"Flask server error: {e}")
                raise
        except Exception as e:
            logger.error(f"Flask server error: {e}", exc_info=True)
            raise


if __name__ == '__main__':
    logger.warning("Running Flask app directly - shared state will not be initialized")
    run_server()
