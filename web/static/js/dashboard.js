/**
 * PlayAble Dashboard
 */

// ── State ────────────────────────────────────────────────────────────────────
let btScanInterval = null;
let ps5Connected = false;

// ── Init ─────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initEventListeners();
    loadPS5Devices();
    startStatusPolling();
    loadMappings();
    loadThresholds();
});

// ── Event listeners ──────────────────────────────────────────────────────────
function initEventListeners() {
    // PSN auth flow
    document.getElementById('btn-psn-login').addEventListener('click', startPSNLogin);
    document.getElementById('btn-copy-url').addEventListener('click', copyAuthUrl);
    document.getElementById('btn-submit-redirect').addEventListener('click', submitRedirect);
    document.getElementById('btn-submit-pin').addEventListener('click', submitPin);

    // Register New PS5 toggle
    document.getElementById('btn-add-ps5').addEventListener('click', () => {
        document.getElementById('new-ps5-section').classList.remove('hidden');
        document.getElementById('btn-add-ps5').classList.add('hidden');
    });

    // Bluetooth pairing
    document.getElementById('btn-bt-scan').addEventListener('click', startBTScan);
    document.getElementById('btn-bt-stop').addEventListener('click', stopBTScan);

    // Thresholds
    document.getElementById('delta-threshold').addEventListener('input', () => {
        document.getElementById('delta-value').textContent =
            document.getElementById('delta-threshold').value;
    });
    document.getElementById('raise-minimum').addEventListener('input', () => {
        document.getElementById('raise-value').textContent =
            document.getElementById('raise-minimum').value;
    });
    document.getElementById('btn-update-thresholds').addEventListener('click', updateThresholds);

    // Mappings
    document.getElementById('btn-add-mapping').addEventListener('click', addMapping);
}

// ── PS5 Device List ───────────────────────────────────────────────────────────
async function loadPS5Devices() {
    try {
        const res = await fetch('/api/ps5/devices');
        const data = await res.json();

        const savedSection = document.getElementById('saved-devices-section');
        const newSection   = document.getElementById('new-ps5-section');
        const list         = document.getElementById('saved-devices-list');

        if (data.devices && data.devices.length > 0) {
            // Show saved devices
            list.innerHTML = '';
            data.devices.forEach(device => {
                const card = buildDeviceCard(device, data.last_host);
                list.appendChild(card);
            });
            savedSection.classList.remove('hidden');
            newSection.classList.add('hidden');
        } else {
            // No saved devices — show auth flow
            savedSection.classList.add('hidden');
            newSection.classList.remove('hidden');
        }
    } catch (err) {
        console.error('Failed to load PS5 devices:', err);
    }
}

function buildDeviceCard(device, lastHost) {
    const card = document.createElement('div');
    card.className = 'device-card';
    card.dataset.mac = device.mac;

    card.innerHTML = `
        <div class="device-info">
            <span class="device-name">${escHtml(device.nickname)}</span>
            <span class="device-mac">${escHtml(device.mac)}</span>
        </div>
        <div class="device-connect-row">
            <input type="text" class="device-ip-input" placeholder="192.168.0.33"
                   value="${escHtml(lastHost || '')}" title="PS5 IP Address">
            <button class="btn btn-success btn-sm btn-connect-device">Connect</button>
            <button class="btn btn-danger btn-sm btn-disconnect-device hidden">Disconnect</button>
            <span class="device-status-label"></span>
        </div>
    `;

    card.querySelector('.btn-connect-device').addEventListener('click', () => {
        const ip = card.querySelector('.device-ip-input').value.trim();
        if (!ip) {
            showMessage('psn-message', 'Enter the PS5 IP address', 'error');
            return;
        }
        connectToPS5(ip, card);
    });

    card.querySelector('.btn-disconnect-device').addEventListener('click', () => {
        disconnectPS5(card);
    });

    return card;
}

async function connectToPS5(ip, card) {
    const statusLabel   = card.querySelector('.device-status-label');
    const connectBtn    = card.querySelector('.btn-connect-device');
    const disconnectBtn = card.querySelector('.btn-disconnect-device');

    statusLabel.textContent = 'Connecting…';
    statusLabel.className   = 'device-status-label connecting';
    connectBtn.disabled     = true;

    try {
        const res  = await fetch('/api/remoteplay/connect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ps5_host: ip }),
        });
        const data = await res.json();

        if (data.success) {
            statusLabel.textContent = 'Connected';
            statusLabel.className   = 'device-status-label connected';
            connectBtn.classList.add('hidden');
            disconnectBtn.classList.remove('hidden');
            ps5Connected = true;
            showMessage('psn-message', `Connected to PS5 at ${ip}`, 'success');
        } else {
            statusLabel.textContent = 'Failed';
            statusLabel.className   = 'device-status-label failed';
            connectBtn.disabled     = false;
            showMessage('psn-message', `Error: ${data.error}`, 'error');
        }
    } catch (err) {
        statusLabel.textContent = 'Error';
        statusLabel.className   = 'device-status-label failed';
        connectBtn.disabled     = false;
        showMessage('psn-message', `Failed to connect: ${err.message}`, 'error');
    }
}

async function disconnectPS5(card) {
    const statusLabel   = card.querySelector('.device-status-label');
    const connectBtn    = card.querySelector('.btn-connect-device');
    const disconnectBtn = card.querySelector('.btn-disconnect-device');

    try {
        const res  = await fetch('/api/remoteplay/disconnect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
        });
        const data = await res.json();

        if (data.success) {
            statusLabel.textContent = '';
            statusLabel.className   = 'device-status-label';
            connectBtn.disabled     = false;
            connectBtn.classList.remove('hidden');
            disconnectBtn.classList.add('hidden');
            ps5Connected = false;
            showMessage('psn-message', 'Disconnected from PS5', 'success');
        } else {
            showMessage('psn-message', `Error: ${data.error}`, 'error');
        }
    } catch (err) {
        showMessage('psn-message', `Failed to disconnect: ${err.message}`, 'error');
    }
}

// ── PSN Auth Flow ─────────────────────────────────────────────────────────────
async function startPSNLogin() {
    try {
        showMessage('psn-message', 'Starting PSN login…', 'info');
        const res  = await fetch('/api/psn/login', { method: 'POST', headers: { 'Content-Type': 'application/json' } });
        const data = await res.json();
        if (data.success) {
            document.getElementById('auth-url').value = data.authorization_url;
            document.getElementById('auth-url-section').classList.remove('hidden');
            document.getElementById('redirect-section').classList.remove('hidden');
            showMessage('psn-message', 'Visit the URL above, then paste the redirect URL', 'success');
        } else {
            showMessage('psn-message', `Error: ${data.error}`, 'error');
        }
    } catch (err) {
        showMessage('psn-message', `Failed: ${err.message}`, 'error');
    }
}

function copyAuthUrl() {
    document.getElementById('auth-url').select();
    document.execCommand('copy');
    showMessage('psn-message', 'URL copied!', 'success');
}

async function submitRedirect() {
    const redirectUrl = document.getElementById('redirect-url').value.trim();
    if (!redirectUrl) { showMessage('psn-message', 'Paste the redirect URL first', 'error'); return; }
    try {
        showMessage('psn-message', 'Processing authentication…', 'info');
        const res  = await fetch('/api/psn/callback', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ redirect_url: redirectUrl }),
        });
        const data = await res.json();
        if (data.success) {
            document.getElementById('redirect-section').classList.add('hidden');
            document.getElementById('pin-section').classList.remove('hidden');
            showMessage('psn-message', 'Authenticated! On PS5: Settings → Remote Play → Link Device → get PIN', 'success');
        } else {
            showMessage('psn-message', `Error: ${data.error}`, 'error');
        }
    } catch (err) {
        showMessage('psn-message', `Failed: ${err.message}`, 'error');
    }
}

async function submitPin() {
    const pin     = document.getElementById('pin-code').value.trim();
    const ps5Host = document.getElementById('ps5-host-pin').value.trim();
    if (!pin || pin.length !== 8) { showMessage('psn-message', 'Enter the 8-digit PIN', 'error'); return; }
    if (!ps5Host) { showMessage('psn-message', 'Enter the PS5 IP address', 'error'); return; }
    try {
        showMessage('psn-message', 'Registering device…', 'info');
        const res  = await fetch('/api/psn/pin', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pin, ps5_host: ps5Host }),
        });
        const data = await res.json();
        if (data.success) {
            showMessage('psn-message', 'Registered! Reloading device list…', 'success');
            setTimeout(() => loadPS5Devices(), 800);
        } else {
            showMessage('psn-message', `Error: ${data.error}`, 'error');
        }
    } catch (err) {
        showMessage('psn-message', `Failed: ${err.message}`, 'error');
    }
}

// ── Bluetooth Pairing ────────────────────────────────────────────────────────
async function startBTScan() {
    document.getElementById('btn-bt-scan').classList.add('hidden');
    document.getElementById('btn-bt-stop').classList.remove('hidden');
    document.getElementById('bt-scan-spinner').classList.remove('hidden');
    document.getElementById('bt-scan-label').classList.remove('hidden');

    const devicesList = document.getElementById('bt-devices-list');
    devicesList.innerHTML = '';
    devicesList.classList.remove('hidden');

    try {
        await fetch('/api/bluetooth/scan/start', { method: 'POST' });
        // Poll for results every 1.5 seconds
        btScanInterval = setInterval(pollBTResults, 1500);
    } catch (err) {
        showMessage('bt-message', `Scan failed: ${err.message}`, 'error');
        resetBTScanUI();
    }
}

async function stopBTScan() {
    clearInterval(btScanInterval);
    btScanInterval = null;
    try {
        await fetch('/api/bluetooth/scan/stop', { method: 'POST' });
    } catch (_) {}
    resetBTScanUI();
    showMessage('bt-message', 'Scan stopped', 'info');
}

function resetBTScanUI() {
    document.getElementById('btn-bt-scan').classList.remove('hidden');
    document.getElementById('btn-bt-stop').classList.add('hidden');
    document.getElementById('bt-scan-spinner').classList.add('hidden');
    document.getElementById('bt-scan-label').classList.add('hidden');
}

async function pollBTResults() {
    try {
        const res  = await fetch('/api/bluetooth/scan/results');
        const data = await res.json();

        renderBTDevices(data.devices || []);

        if (!data.scanning) {
            // Scan ended naturally (15s timeout)
            clearInterval(btScanInterval);
            btScanInterval = null;
            resetBTScanUI();
            showMessage('bt-message',
                data.devices && data.devices.length > 0
                    ? `Found ${data.devices.length} device(s)`
                    : 'No devices found. Make sure the controller is in pairing mode.',
                data.devices && data.devices.length > 0 ? 'success' : 'info');
        }
    } catch (err) {
        console.error('BT poll error:', err);
    }
}

function renderBTDevices(devices) {
    const list = document.getElementById('bt-devices-list');
    // Track existing entries by MAC to avoid full re-render
    const existing = new Set(Array.from(list.querySelectorAll('.bt-device-row')).map(el => el.dataset.mac));

    devices.forEach(dev => {
        if (existing.has(dev.mac)) return; // already shown
        const row = document.createElement('div');
        row.className = 'bt-device-row';
        row.dataset.mac = dev.mac;
        row.innerHTML = `
            <div class="bt-device-info">
                <span class="bt-device-name">${escHtml(dev.name)}</span>
                <span class="bt-device-mac">${escHtml(dev.mac)}</span>
            </div>
            <button class="btn btn-primary btn-sm btn-bt-pair">Pair</button>
            <span class="bt-pair-status"></span>
        `;
        row.querySelector('.btn-bt-pair').addEventListener('click', () => pairBTDevice(dev.mac, row));
        list.appendChild(row);
    });
}

async function pairBTDevice(mac, row) {
    const btn        = row.querySelector('.btn-bt-pair');
    const statusSpan = row.querySelector('.bt-pair-status');

    btn.disabled         = true;
    statusSpan.textContent = 'Pairing…';
    statusSpan.className   = 'bt-pair-status pairing';

    // Stop scan first
    clearInterval(btScanInterval);
    btScanInterval = null;
    resetBTScanUI();

    try {
        const res  = await fetch('/api/bluetooth/pair', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mac }),
        });
        const data = await res.json();

        if (data.success) {
            statusSpan.textContent = 'Paired!';
            statusSpan.className   = 'bt-pair-status paired';
            showMessage('bt-message', `${mac} paired successfully`, 'success');
        } else {
            const detail = data.results
                ? Object.entries(data.results).map(([k, v]) => `${k}:${v ? '✓' : '✗'}`).join(' ')
                : data.error;
            statusSpan.textContent = 'Failed';
            statusSpan.className   = 'bt-pair-status failed';
            btn.disabled           = false;
            showMessage('bt-message', `Pairing failed — ${detail}`, 'error');
        }
    } catch (err) {
        statusSpan.textContent = 'Error';
        statusSpan.className   = 'bt-pair-status failed';
        btn.disabled           = false;
        showMessage('bt-message', `Error: ${err.message}`, 'error');
    }
}

// ── Status Polling ───────────────────────────────────────────────────────────
function startStatusPolling() {
    setInterval(updateStatus, 2000);
    updateStatus();
}

async function updateStatus() {
    try {
        const res    = await fetch('/api/status');
        const status = await res.json();

        setStatusIcon('status-psn-auth', status.psn_authenticated);
        setStatusIcon('status-ps5',      status.ps5_connected);
        setStatusIcon('status-camera',   status.camera_active);
        document.getElementById('status-fps').textContent = (status.fps || 0).toFixed(1);

        // Controller with name
        const ctrlEl = document.getElementById('status-controller');
        if (status.controller_connected) {
            ctrlEl.textContent = '✅';
            ctrlEl.title       = status.controller_name || 'Connected';
        } else {
            ctrlEl.textContent = '❌';
            ctrlEl.title       = '';
        }

        // Controller panel badge
        const badge = document.getElementById('controller-badge');
        const nameLabel = document.getElementById('controller-name-label');
        if (status.controller_connected) {
            badge.textContent = 'Connected';
            badge.className   = 'status-badge connected';
            nameLabel.textContent = status.controller_name || '';
        } else {
            badge.textContent = 'Not Connected';
            badge.className   = 'status-badge disconnected';
            nameLabel.textContent = '';
        }

        // Sync PS5 device card disconnect button visibility
        if (ps5Connected && !status.ps5_connected) {
            // Session dropped externally
            ps5Connected = false;
            document.querySelectorAll('.btn-disconnect-device').forEach(btn => {
                btn.classList.add('hidden');
            });
            document.querySelectorAll('.btn-connect-device').forEach(btn => {
                btn.classList.remove('hidden');
                btn.disabled = false;
            });
            document.querySelectorAll('.device-status-label').forEach(el => {
                el.textContent = 'Disconnected';
                el.className   = 'device-status-label failed';
            });
        }

    } catch (err) {
        console.error('Status poll error:', err);
    }
}

function setStatusIcon(id, active) {
    document.getElementById(id).textContent = active ? '✅' : '❌';
}

// ── Thresholds ───────────────────────────────────────────────────────────────
async function loadThresholds() {
    try {
        const res  = await fetch('/api/thresholds');
        const data = await res.json();
        if (data.delta_threshold !== undefined) {
            document.getElementById('delta-threshold').value = data.delta_threshold;
            document.getElementById('delta-value').textContent = data.delta_threshold;
        }
        if (data.raise_minimum !== undefined) {
            document.getElementById('raise-minimum').value = data.raise_minimum;
            document.getElementById('raise-value').textContent = data.raise_minimum;
        }
    } catch (err) {
        console.error('Failed to load thresholds:', err);
    }
}

async function updateThresholds() {
    const delta = parseFloat(document.getElementById('delta-threshold').value);
    const raise = parseFloat(document.getElementById('raise-minimum').value);
    try {
        showMessage('threshold-message', 'Updating…', 'info');
        const res  = await fetch('/api/thresholds', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ delta_threshold: delta, raise_minimum: raise }),
        });
        const data = await res.json();
        showMessage('threshold-message',
            data.success ? 'Thresholds updated!' : `Error: ${data.error}`,
            data.success ? 'success' : 'error');
    } catch (err) {
        showMessage('threshold-message', `Failed: ${err.message}`, 'error');
    }
}

// ── Gesture Mappings ──────────────────────────────────────────────────────────
async function loadMappings() {
    try {
        const res      = await fetch('/api/mappings');
        const mappings = await res.json();
        const list     = document.getElementById('mappings-list');
        list.innerHTML = '';

        if (Object.keys(mappings).length === 0) {
            list.innerHTML = '<li class="no-mappings">No active mappings</li>';
            return;
        }
        for (const [gesture, button] of Object.entries(mappings)) {
            const li = document.createElement('li');
            li.className = 'mapping-item';
            li.innerHTML = `
                <span class="mapping-text">${fmtGesture(gesture)} → ${escHtml(button)}</span>
                <button class="btn btn-small btn-danger" onclick="removeMapping('${escHtml(gesture)}')">Remove</button>
            `;
            list.appendChild(li);
        }
    } catch (err) {
        console.error('Failed to load mappings:', err);
    }
}

async function addMapping() {
    const gesture = document.getElementById('gesture-select').value;
    const button  = document.getElementById('button-select').value;
    try {
        showMessage('mapping-message', 'Adding mapping…', 'info');
        const res  = await fetch('/api/mappings', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ gesture_name: gesture, button }),
        });
        const data = await res.json();
        showMessage('mapping-message',
            data.success ? 'Mapping added!' : `Error: ${data.error}`,
            data.success ? 'success' : 'error');
        if (data.success) loadMappings();
    } catch (err) {
        showMessage('mapping-message', `Failed: ${err.message}`, 'error');
    }
}

async function removeMapping(gestureName) {
    try {
        showMessage('mapping-message', 'Removing…', 'info');
        const res  = await fetch('/api/mappings', {
            method: 'DELETE', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ gesture_name: gestureName }),
        });
        const data = await res.json();
        showMessage('mapping-message',
            data.success ? 'Mapping removed!' : `Error: ${data.error}`,
            data.success ? 'success' : 'error');
        if (data.success) loadMappings();
    } catch (err) {
        showMessage('mapping-message', `Failed: ${err.message}`, 'error');
    }
}

// ── Utilities ─────────────────────────────────────────────────────────────────
function showMessage(id, text, type) {
    const el = document.getElementById(id);
    el.textContent = text;
    el.className   = `message ${type}`;
    el.classList.remove('hidden');
    clearTimeout(el._hideTimer);
    el._hideTimer = setTimeout(() => el.classList.add('hidden'), 6000);
}

function fmtGesture(name) {
    return name.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
}

function escHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}
