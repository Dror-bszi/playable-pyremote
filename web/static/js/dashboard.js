/**
 * PlayAble Dashboard JavaScript
 * Handles PSN authentication, status polling, threshold updates, and gesture mapping management
 */

// State management
let statusPollInterval = null;
let currentAuthUrl = null;

// Initialize dashboard on page load
document.addEventListener('DOMContentLoaded', () => {
    initializeEventListeners();
    startStatusPolling();
    loadMappings();
    loadThresholds();
});

/**
 * Initialize all event listeners
 */
function initializeEventListeners() {
    // PSN Connection
    document.getElementById('btn-psn-login').addEventListener('click', startPSNLogin);
    document.getElementById('btn-copy-url').addEventListener('click', copyAuthUrl);
    document.getElementById('btn-submit-redirect').addEventListener('click', submitRedirect);
    document.getElementById('btn-submit-pin').addEventListener('click', submitPin);
    document.getElementById('btn-connect').addEventListener('click', connectRemotePlay);
    document.getElementById('btn-disconnect').addEventListener('click', disconnectRemotePlay);
    
    // Threshold Controls
    document.getElementById('delta-threshold').addEventListener('input', updateDeltaDisplay);
    document.getElementById('raise-minimum').addEventListener('input', updateRaiseDisplay);
    document.getElementById('btn-update-thresholds').addEventListener('click', updateThresholds);
    
    // Gesture Mapping
    document.getElementById('btn-add-mapping').addEventListener('click', addMapping);
}

/**
 * PSN Authentication Flow
 */
async function startPSNLogin() {
    try {
        showMessage('psn-message', 'Starting PSN login...', 'info');
        
        const response = await fetch('/api/psn/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const data = await response.json();
        
        if (data.success) {
            currentAuthUrl = data.authorization_url;
            document.getElementById('auth-url').value = currentAuthUrl;
            document.getElementById('auth-url-section').classList.remove('hidden');
            document.getElementById('redirect-section').classList.remove('hidden');
            showMessage('psn-message', 'Please visit the URL above to authenticate', 'success');
        } else {
            showMessage('psn-message', `Error: ${data.error}`, 'error');
        }
    } catch (error) {
        showMessage('psn-message', `Failed to start login: ${error.message}`, 'error');
    }
}

function copyAuthUrl() {
    const authUrlInput = document.getElementById('auth-url');
    authUrlInput.select();
    document.execCommand('copy');
    showMessage('psn-message', 'URL copied to clipboard!', 'success');
}

async function submitRedirect() {
    const redirectUrl = document.getElementById('redirect-url').value.trim();
    
    if (!redirectUrl) {
        showMessage('psn-message', 'Please enter the redirect URL', 'error');
        return;
    }
    
    try {
        showMessage('psn-message', 'Processing authentication...', 'info');
        
        const response = await fetch('/api/psn/callback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ redirect_url: redirectUrl })
        });
        
        const data = await response.json();
        
        if (data.success) {
            document.getElementById('redirect-section').classList.add('hidden');
            document.getElementById('pin-section').classList.remove('hidden');
            showMessage('psn-message', 'Authentication successful! Now enter the PIN from your PS5', 'success');
        } else {
            showMessage('psn-message', `Error: ${data.error}`, 'error');
        }
    } catch (error) {
        showMessage('psn-message', `Failed to process redirect: ${error.message}`, 'error');
    }
}

async function submitPin() {
    const pin = document.getElementById('pin-code').value.trim();
    
    if (!pin || pin.length !== 8) {
        showMessage('psn-message', 'Please enter an 8-digit PIN', 'error');
        return;
    }
    
    try {
        showMessage('psn-message', 'Registering device...', 'info');
        
        const response = await fetch('/api/psn/pin', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pin: pin })
        });
        
        const data = await response.json();
        
        if (data.success) {
            document.getElementById('pin-section').classList.add('hidden');
            document.getElementById('connection-section').classList.remove('hidden');
            showMessage('psn-message', 'Device registered! You can now connect to your PS5', 'success');
        } else {
            showMessage('psn-message', `Error: ${data.error}`, 'error');
        }
    } catch (error) {
        showMessage('psn-message', `Failed to register device: ${error.message}`, 'error');
    }
}

async function connectRemotePlay() {
    const ps5Host = document.getElementById('ps5-host').value.trim();
    
    try {
        showMessage('psn-message', 'Connecting to PS5...', 'info');
        
        const response = await fetch('/api/remoteplay/connect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ps5_host: ps5Host || null })
        });
        
        const data = await response.json();
        
        if (data.success) {
            document.getElementById('btn-connect').classList.add('hidden');
            document.getElementById('btn-disconnect').classList.remove('hidden');
            showMessage('psn-message', 'Connected to PS5!', 'success');
        } else {
            showMessage('psn-message', `Error: ${data.error}`, 'error');
        }
    } catch (error) {
        showMessage('psn-message', `Failed to connect: ${error.message}`, 'error');
    }
}

async function disconnectRemotePlay() {
    try {
        showMessage('psn-message', 'Disconnecting...', 'info');
        
        const response = await fetch('/api/remoteplay/disconnect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const data = await response.json();
        
        if (data.success) {
            document.getElementById('btn-connect').classList.remove('hidden');
            document.getElementById('btn-disconnect').classList.add('hidden');
            showMessage('psn-message', 'Disconnected from PS5', 'success');
        } else {
            showMessage('psn-message', `Error: ${data.error}`, 'error');
        }
    } catch (error) {
        showMessage('psn-message', `Failed to disconnect: ${error.message}`, 'error');
    }
}

/**
 * Status Polling
 */
function startStatusPolling() {
    // Poll every 2 seconds
    statusPollInterval = setInterval(updateStatus, 2000);
    updateStatus(); // Initial update
}

async function updateStatus() {
    try {
        const response = await fetch('/api/status');
        const status = await response.json();
        
        // Update status indicators
        updateStatusIndicator('status-psn-auth', status.psn_authenticated);
        updateStatusIndicator('status-ps5', status.ps5_connected);
        updateStatusIndicator('status-controller', status.controller_connected);
        updateStatusIndicator('status-camera', status.camera_active);
        document.getElementById('status-fps').textContent = status.fps.toFixed(1);
        
        // Update PSN auth status text
        const psnAuthStatus = document.getElementById('psn-auth-status');
        if (status.psn_authenticated) {
            psnAuthStatus.textContent = 'Authenticated';
            psnAuthStatus.classList.add('authenticated');
            document.getElementById('connection-section').classList.remove('hidden');
        } else {
            psnAuthStatus.textContent = 'Not Authenticated';
            psnAuthStatus.classList.remove('authenticated');
        }
        
        // Update connect/disconnect button visibility
        if (status.ps5_connected) {
            document.getElementById('btn-connect').classList.add('hidden');
            document.getElementById('btn-disconnect').classList.remove('hidden');
        } else {
            document.getElementById('btn-connect').classList.remove('hidden');
            document.getElementById('btn-disconnect').classList.add('hidden');
        }
        
    } catch (error) {
        console.error('Failed to update status:', error);
    }
}

function updateStatusIndicator(elementId, isActive) {
    const element = document.getElementById(elementId);
    element.textContent = isActive ? '✅' : '❌';
}

/**
 * Threshold Controls
 */
function updateDeltaDisplay() {
    const value = document.getElementById('delta-threshold').value;
    document.getElementById('delta-value').textContent = value;
}

function updateRaiseDisplay() {
    const value = document.getElementById('raise-minimum').value;
    document.getElementById('raise-value').textContent = value;
}

async function loadThresholds() {
    try {
        const response = await fetch('/api/thresholds');
        const thresholds = await response.json();
        
        if (thresholds.delta_threshold !== undefined) {
            document.getElementById('delta-threshold').value = thresholds.delta_threshold;
            document.getElementById('delta-value').textContent = thresholds.delta_threshold;
        }
        
        if (thresholds.raise_minimum !== undefined) {
            document.getElementById('raise-minimum').value = thresholds.raise_minimum;
            document.getElementById('raise-value').textContent = thresholds.raise_minimum;
        }
    } catch (error) {
        console.error('Failed to load thresholds:', error);
    }
}

async function updateThresholds() {
    const deltaThreshold = parseFloat(document.getElementById('delta-threshold').value);
    const raiseMinimum = parseFloat(document.getElementById('raise-minimum').value);
    
    try {
        showMessage('threshold-message', 'Updating thresholds...', 'info');
        
        const response = await fetch('/api/thresholds', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                delta_threshold: deltaThreshold,
                raise_minimum: raiseMinimum
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showMessage('threshold-message', 'Thresholds updated successfully!', 'success');
        } else {
            showMessage('threshold-message', `Error: ${data.error}`, 'error');
        }
    } catch (error) {
        showMessage('threshold-message', `Failed to update thresholds: ${error.message}`, 'error');
    }
}

/**
 * Gesture Mapping Management
 */
async function loadMappings() {
    try {
        const response = await fetch('/api/mappings');
        const mappings = await response.json();
        
        const mappingsList = document.getElementById('mappings-list');
        mappingsList.innerHTML = '';
        
        if (Object.keys(mappings).length === 0) {
            mappingsList.innerHTML = '<li class="no-mappings">No active mappings</li>';
            return;
        }
        
        for (const [gesture, button] of Object.entries(mappings)) {
            const li = document.createElement('li');
            li.className = 'mapping-item';
            li.innerHTML = `
                <span class="mapping-text">${formatGestureName(gesture)} → ${button}</span>
                <button class="btn btn-small btn-danger" onclick="removeMapping('${gesture}')">Remove</button>
            `;
            mappingsList.appendChild(li);
        }
    } catch (error) {
        console.error('Failed to load mappings:', error);
    }
}

async function addMapping() {
    const gestureName = document.getElementById('gesture-select').value;
    const button = document.getElementById('button-select').value;
    
    try {
        showMessage('mapping-message', 'Adding mapping...', 'info');
        
        const response = await fetch('/api/mappings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                gesture_name: gestureName,
                button: button
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showMessage('mapping-message', 'Mapping added successfully!', 'success');
            loadMappings(); // Refresh the list
        } else {
            showMessage('mapping-message', `Error: ${data.error}`, 'error');
        }
    } catch (error) {
        showMessage('mapping-message', `Failed to add mapping: ${error.message}`, 'error');
    }
}

async function removeMapping(gestureName) {
    try {
        showMessage('mapping-message', 'Removing mapping...', 'info');
        
        const response = await fetch('/api/mappings', {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ gesture_name: gestureName })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showMessage('mapping-message', 'Mapping removed successfully!', 'success');
            loadMappings(); // Refresh the list
        } else {
            showMessage('mapping-message', `Error: ${data.error}`, 'error');
        }
    } catch (error) {
        showMessage('mapping-message', `Failed to remove mapping: ${error.message}`, 'error');
    }
}

/**
 * Utility Functions
 */
function showMessage(elementId, message, type) {
    const messageElement = document.getElementById(elementId);
    messageElement.textContent = message;
    messageElement.className = `message ${type}`;
    messageElement.classList.remove('hidden');
    
    // Auto-hide after 5 seconds
    setTimeout(() => {
        messageElement.classList.add('hidden');
    }, 5000);
}

function formatGestureName(gesture) {
    return gesture
        .split('_')
        .map(word => word.charAt(0).toUpperCase() + word.slice(1))
        .join(' ');
}
