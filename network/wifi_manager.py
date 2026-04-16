"""
WiFi Manager for PlayAble.

Manages WiFi station / hotspot (AP) mode via NetworkManager (nmcli).
Reads the RPi serial number to generate a stable device ID, SSID and hostname.
"""

import os
import re
import time
import logging
import subprocess
from typing import Optional, List, Dict, Tuple

logger = logging.getLogger(__name__)

HOTSPOT_CON_NAME = 'PlayAble-Hotspot'
HOTSPOT_IP       = '192.168.4.1'
_NM_DNSMASQ_DIR  = '/etc/NetworkManager/dnsmasq-shared.d'
_NM_CAPTIVE_CONF = os.path.join(_NM_DNSMASQ_DIR, 'playable-captive.conf')


def _get_serial() -> str:
    """Read RPi CPU serial from /proc/cpuinfo."""
    try:
        with open('/proc/cpuinfo') as f:
            for line in f:
                if line.startswith('Serial'):
                    return line.split(':')[1].strip()
    except Exception:
        pass
    return ''


def get_device_id() -> str:
    """Return last 4 chars of RPi serial, uppercase.  E.g. 'C0E1'."""
    s = _get_serial()
    return s[-4:].upper() if len(s) >= 4 else 'XXXX'


def get_hotspot_ssid() -> str:
    return f'PlayAble-{get_device_id()}'


def get_hostname() -> str:
    return f'playable-{get_device_id().lower()}'


class WiFiManager:
    """
    Manages WiFi station and hotspot (AP) modes via nmcli.

    Hotspot:
    - SSID:  PlayAble-XXXX  (open, no password)
    - IP:    192.168.4.1/24
    - DHCP:  NetworkManager shared mode (built-in)
    - DNS:   NM dnsmasq with address=/#/192.168.4.1 (captive portal)
    - Port:  iptables redirects :80 → Flask :5000
    """

    def __init__(self):
        self._hotspot_active = False
        self.device_id   = get_device_id()
        self.hotspot_ssid = get_hotspot_ssid()
        self.hostname    = get_hostname()
        logger.info(
            f'WiFiManager: device_id={self.device_id}  '
            f'ssid={self.hotspot_ssid}  hostname={self.hostname}'
        )

    # ── Connection checks ────────────────────────────────────────────────────

    def is_wifi_connected(self) -> bool:
        """True if wlan0 is connected to a WiFi network as a station."""
        if self._hotspot_active:
            return False
        try:
            r = subprocess.run(
                ['nmcli', '-t', '-f', 'ACTIVE,BSSID', 'dev', 'wifi'],
                capture_output=True, text=True, timeout=5,
            )
            for line in r.stdout.splitlines():
                parts = line.split(':', 1)
                if len(parts) == 2 and parts[0] == 'yes':
                    return True
        except Exception as e:
            logger.debug(f'is_wifi_connected: {e}')
        return False

    def get_current_ssid(self) -> Optional[str]:
        """Return the SSID of the currently connected WiFi network, or None."""
        try:
            r = subprocess.run(
                ['nmcli', '-t', '-f', 'ACTIVE,SSID', 'dev', 'wifi'],
                capture_output=True, text=True, timeout=5,
            )
            for line in r.stdout.splitlines():
                parts = line.split(':', 1)
                if len(parts) == 2 and parts[0] == 'yes':
                    return parts[1].strip()
        except Exception:
            pass
        return None

    def wait_for_wifi(self, timeout_seconds: int = 20) -> bool:
        """
        Poll until wlan0 has a station WiFi connection or timeout expires.
        Returns True if connected.
        """
        logger.info(f'WiFiManager: waiting up to {timeout_seconds}s for WiFi…')
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if self.is_wifi_connected():
                ssid = self.get_current_ssid() or '(unknown)'
                logger.info(f'WiFiManager: connected to "{ssid}"')
                return True
            time.sleep(2)
        logger.info('WiFiManager: WiFi not available after timeout')
        return False

    # ── Hotspot helpers ──────────────────────────────────────────────────────

    def _write_captive_portal_config(self):
        """
        Write NM dnsmasq drop-in that resolves ALL domains to the hotspot IP.
        Must be done BEFORE bringing up the NM shared AP so NM's dnsmasq picks it up.
        """
        content = f'address=/#/{HOTSPOT_IP}\n'
        try:
            subprocess.run(['sudo', 'mkdir', '-p', _NM_DNSMASQ_DIR],
                           capture_output=True, timeout=5)
            r = subprocess.run(
                ['sudo', 'tee', _NM_CAPTIVE_CONF],
                input=content, capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0:
                logger.info(f'Captive portal DNS config → {_NM_CAPTIVE_CONF}')
            else:
                logger.warning(f'Could not write captive portal config: {r.stderr.strip()}')
        except Exception as e:
            logger.warning(f'_write_captive_portal_config: {e}')

    def _remove_captive_portal_config(self):
        try:
            subprocess.run(['sudo', 'rm', '-f', _NM_CAPTIVE_CONF],
                           capture_output=True, timeout=5)
        except Exception:
            pass

    def _add_iptables_redirect(self):
        """Redirect incoming TCP :80 on wlan0 → :5000 so Flask handles captive probes."""
        try:
            subprocess.run(
                ['sudo', 'iptables', '-t', 'nat', '-A', 'PREROUTING',
                 '-i', 'wlan0', '-p', 'tcp', '--dport', '80',
                 '-j', 'REDIRECT', '--to-port', '5000'],
                capture_output=True, timeout=5,
            )
            logger.info('iptables: :80 → :5000 redirect added on wlan0')
        except Exception as e:
            logger.warning(f'iptables redirect failed: {e}')

    def _remove_iptables_redirect(self):
        try:
            subprocess.run(
                ['sudo', 'iptables', '-t', 'nat', '-D', 'PREROUTING',
                 '-i', 'wlan0', '-p', 'tcp', '--dport', '80',
                 '-j', 'REDIRECT', '--to-port', '5000'],
                capture_output=True, timeout=5,
            )
        except Exception:
            pass

    def _delete_hotspot_profile(self):
        """Remove the NM hotspot connection profile if it exists."""
        try:
            r = subprocess.run(
                ['sudo', 'nmcli', 'con', 'show', HOTSPOT_CON_NAME],
                capture_output=True, timeout=5,
            )
            if r.returncode == 0:
                subprocess.run(
                    ['sudo', 'nmcli', 'con', 'delete', HOTSPOT_CON_NAME],
                    capture_output=True, timeout=10,
                )
                logger.info(f'Deleted NM profile: {HOTSPOT_CON_NAME}')
        except Exception as e:
            logger.debug(f'_delete_hotspot_profile: {e}')

    # ── Public API ───────────────────────────────────────────────────────────

    def start_hotspot(self) -> bool:
        """
        Start the PlayAble WiFi hotspot (open network, no password).
        NM shared mode provides DHCP; NM dnsmasq provides captive portal DNS.
        iptables redirects port 80 → 5000 for OS captive portal probes.

        NOTE: activating AP mode takes wlan0 out of station mode, which will
        terminate any SSH session running over WiFi — this is expected behaviour.

        Returns True on success.
        """
        try:
            # Write captive portal config before NM starts its dnsmasq
            self._write_captive_portal_config()

            # Remove any stale profile from a previous run
            self._delete_hotspot_profile()

            logger.info(
                f'Creating hotspot: SSID="{self.hotspot_ssid}" IP={HOTSPOT_IP}'
            )
            r = subprocess.run(
                [
                    'sudo', 'nmcli', 'con', 'add',
                    'type', 'wifi',
                    'ifname', 'wlan0',
                    'con-name', HOTSPOT_CON_NAME,
                    'autoconnect', 'no',
                    'ssid', self.hotspot_ssid,
                    'mode', 'ap',
                    'ipv4.method', 'shared',
                    'ipv4.addresses', f'{HOTSPOT_IP}/24',
                ],
                capture_output=True, text=True, timeout=15,
            )
            if r.returncode != 0:
                logger.error(f'nmcli con add failed: {r.stderr.strip()}')
                return False

            # Bring up in the background.  nmcli con up may never return over SSH
            # because wlan0 switching to AP mode kills the SSH channel.
            # main.py running locally (or as a service) is unaffected.
            subprocess.Popen(
                ['sudo', 'nmcli', 'con', 'up', HOTSPOT_CON_NAME],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(4)   # let AP come up

            self._add_iptables_redirect()
            self._hotspot_active = True
            logger.info(f'Hotspot active: "{self.hotspot_ssid}" at {HOTSPOT_IP}')
            return True

        except Exception as e:
            logger.error(f'start_hotspot: {e}')
            return False

    def stop_hotspot(self):
        """Tear down the hotspot and clean up all side effects."""
        if not self._hotspot_active:
            return
        self._remove_iptables_redirect()
        self._delete_hotspot_profile()
        self._remove_captive_portal_config()
        self._hotspot_active = False
        logger.info('Hotspot stopped')

    def get_available_networks(self) -> List[Dict[str, str]]:
        """
        Trigger a WiFi rescan and return visible networks sorted by signal strength.
        Each entry: {'ssid': str, 'signal': str, 'security': str}.
        """
        try:
            subprocess.run(
                ['sudo', 'nmcli', 'dev', 'wifi', 'rescan'],
                capture_output=True, timeout=10,
            )
            time.sleep(2)
            r = subprocess.run(
                ['nmcli', '-t', '-f', 'SSID,SIGNAL,SECURITY', 'dev', 'wifi', 'list'],
                capture_output=True, text=True, timeout=10,
            )
            networks: List[Dict] = []
            seen: set = set()
            for line in r.stdout.splitlines():
                parts = line.split(':', 2)
                if len(parts) < 3:
                    continue
                ssid, signal, security = parts[0].strip(), parts[1].strip(), parts[2].strip()
                if not ssid or ssid in seen or ssid == self.hotspot_ssid:
                    continue
                seen.add(ssid)
                networks.append({'ssid': ssid, 'signal': signal, 'security': security})
            networks.sort(
                key=lambda n: int(n['signal']) if n['signal'].isdigit() else 0,
                reverse=True,
            )
            return networks
        except Exception as e:
            logger.error(f'get_available_networks: {e}')
            return []

    def connect_to_wifi(self, ssid: str, password: str) -> Tuple[bool, str]:
        """
        Connect wlan0 to a WiFi network.
        Stops the hotspot first (wlan0 must be free for station mode).
        Returns (success, message).
        """
        try:
            self.stop_hotspot()
            time.sleep(1)
            logger.info(f'Connecting to WiFi: "{ssid}"')
            cmd = ['sudo', 'nmcli', 'dev', 'wifi', 'connect', ssid]
            if password:
                cmd += ['password', password]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                logger.info(f'Connected to "{ssid}"')
                return True, f'Connected to {ssid}'
            err = (r.stderr or r.stdout or 'unknown error').strip()
            logger.warning(f'WiFi connect failed: {err}')
            return False, err
        except subprocess.TimeoutExpired:
            return False, 'Connection timed out'
        except Exception as e:
            logger.error(f'connect_to_wifi: {e}')
            return False, str(e)

    def get_status(self) -> Dict:
        """
        Return current network status.
        mode: 'hotspot' | 'wifi' | 'offline'
        """
        if self._hotspot_active:
            return {'mode': 'hotspot', 'ssid': self.hotspot_ssid, 'ip': HOTSPOT_IP}
        if self.is_wifi_connected():
            return {
                'mode': 'wifi',
                'ssid': self.get_current_ssid(),
                'ip': self._get_wlan_ip(),
            }
        return {'mode': 'offline', 'ssid': None, 'ip': None}

    def _get_wlan_ip(self) -> Optional[str]:
        try:
            r = subprocess.run(
                ['ip', '-4', '-o', 'addr', 'show', 'wlan0'],
                capture_output=True, text=True, timeout=3,
            )
            m = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', r.stdout)
            return m.group(1) if m else None
        except Exception:
            return None
