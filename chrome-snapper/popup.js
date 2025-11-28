// Load saved settings
chrome.storage.sync.get(['endpoint', 'textMessage', 'hidden', 'captureMode'], (result) => {
  if (result.endpoint) {
    document.getElementById('endpoint').value = result.endpoint;
  }
  if (result.textMessage) {
    document.getElementById('textMessage').value = result.textMessage;
  }
  if (result.hidden !== undefined) {
    document.getElementById('hidden').checked = result.hidden;
  }
  if (result.captureMode) {
    document.querySelector(`input[name="captureMode"][value="${result.captureMode}"]`).checked = true;
  }
});

// Handle capture button click
document.getElementById('capture').addEventListener('click', async () => {
  const endpoint = document.getElementById('endpoint').value.trim();
  const textMessage = document.getElementById('textMessage').value.trim();
  const hidden = document.getElementById('hidden').checked;
  const captureMode = document.querySelector('input[name="captureMode"]:checked').value;
  const statusDiv = document.getElementById('status');
  const captureBtn = document.getElementById('capture');

  if (!endpoint) {
    showStatus('Please enter a server address', 'error');
    return;
  }

  // Validate URL
  try {
    new URL(endpoint);
  } catch (e) {
    showStatus('Invalid URL format', 'error');
    return;
  }

  // Save settings
  chrome.storage.sync.set({ endpoint, textMessage, hidden, captureMode });

  // Append /send-messages to the endpoint
  const fullEndpoint = endpoint.replace(/\/$/, '') + '/send-messages';

  // Disable button and show progress
  captureBtn.disabled = true;
  showStatus('Starting capture...', 'info');

  try {
    // Get active tab
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    // Send message to background script to start capture
    chrome.runtime.sendMessage({
      action: 'captureFullPage',
      tabId: tab.id,
      endpoint: fullEndpoint,
      textMessage: textMessage,
      hidden: hidden,
      captureMode: captureMode
    }, (response) => {
      captureBtn.disabled = false;

      if (response && response.success) {
        const msg = response.mode === 'text'
          ? 'Success! Sent page content as markdown'
          : `Success! Sent ${response.tileCount} tiles`;
        showStatus(msg, 'success');
      } else {
        showStatus(`Error: ${response?.error || 'Unknown error'}`, 'error');
      }
    });

    // Listen for progress updates
    chrome.runtime.onMessage.addListener((message) => {
      if (message.action === 'captureProgress') {
        showStatus(`Sending tile ${message.current}/${message.total}...`, 'info');
      }
    });

  } catch (error) {
    captureBtn.disabled = false;
    showStatus(`Error: ${error.message}`, 'error');
  }
});

function showStatus(message, type) {
  const statusDiv = document.getElementById('status');
  statusDiv.textContent = message;
  statusDiv.className = type;
}