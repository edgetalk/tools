// Background service worker for capture orchestration

// ============================================================
// WebSocket Automation
// ============================================================

let ws = null;
let wsUrl = null;
let reconnectAttempts = 0;
let reconnectTimeout = null;
let isConnecting = false;

// Initialize WebSocket connection from stored URL
chrome.storage.sync.get(['wsUrl'], (result) => {
  if (result.wsUrl) {
    wsUrl = result.wsUrl;
    connectWebSocket();
  }
});

// Listen for tab updates to notify server
chrome.tabs.onActivated.addListener(async (activeInfo) => {
  if (ws && ws.readyState === WebSocket.OPEN) {
    try {
      const tab = await chrome.tabs.get(activeInfo.tabId);
      sendWsMessage({
        type: 'tabUpdate',
        tabId: tab.id,
        url: tab.url,
        title: tab.title
      });
    } catch (e) {
      console.error('Error getting tab info:', e);
    }
  }
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (ws && ws.readyState === WebSocket.OPEN && changeInfo.status === 'complete') {
    sendWsMessage({
      type: 'tabUpdate',
      tabId: tabId,
      url: tab.url,
      title: tab.title
    });
  }
});

function connectWebSocket() {
  if (!wsUrl || isConnecting) return;
  if (ws && ws.readyState === WebSocket.OPEN) return;

  isConnecting = true;
  console.log('Connecting to WebSocket:', wsUrl);

  try {
    ws = new WebSocket(wsUrl);

    ws.onopen = async () => {
      console.log('WebSocket connected');
      isConnecting = false;
      reconnectAttempts = 0;

      // Notify popup of connection status
      broadcastConnectionStatus(true);

      // Send connected message with active tab info
      try {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        if (tab) {
          sendWsMessage({
            type: 'connected',
            tabId: tab.id,
            url: tab.url,
            title: tab.title
          });
        }
      } catch (e) {
        sendWsMessage({ type: 'connected' });
      }
    };

    ws.onmessage = async (event) => {
      try {
        const command = JSON.parse(event.data);
        await handleWsCommand(command);
      } catch (e) {
        console.error('Error handling WebSocket message:', e);
      }
    };

    ws.onclose = () => {
      console.log('WebSocket disconnected');
      isConnecting = false;
      ws = null;
      broadcastConnectionStatus(false);
      scheduleReconnect();
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      isConnecting = false;
    };

  } catch (e) {
    console.error('Failed to create WebSocket:', e);
    isConnecting = false;
    scheduleReconnect();
  }
}

function disconnectWebSocket() {
  if (reconnectTimeout) {
    clearTimeout(reconnectTimeout);
    reconnectTimeout = null;
  }
  reconnectAttempts = 0;

  if (ws) {
    ws.close();
    ws = null;
  }
  broadcastConnectionStatus(false);
}

function scheduleReconnect() {
  if (!wsUrl) return;

  // Exponential backoff: 1s, 2s, 4s, 8s, max 30s
  const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000);
  reconnectAttempts++;

  console.log(`Scheduling reconnect in ${delay}ms (attempt ${reconnectAttempts})`);

  reconnectTimeout = setTimeout(() => {
    reconnectTimeout = null;
    connectWebSocket();
  }, delay);
}

function sendWsMessage(message) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(message));
  }
}

function broadcastConnectionStatus(connected) {
  chrome.runtime.sendMessage({
    action: 'wsStatusUpdate',
    connected: connected
  }).catch(() => {
    // Popup might not be open, ignore
  });
}

async function handleWsCommand(command) {
  const { type, requestId, tabId } = command;

  try {
    let result;

    switch (type) {
      case 'getElements':
        result = await executeInTab(tabId, 'getInteractiveElements', {});
        break;

      case 'getContent':
        result = await executeInTab(tabId, 'extractPageContent', {});
        break;

      case 'click':
        if (command.selector) {
          result = await executeInTab(tabId, 'clickElement', { selector: command.selector });
        } else if (command.x !== undefined && command.y !== undefined) {
          result = await executeInTab(tabId, 'clickElement', { x: command.x, y: command.y });
        } else {
          result = { success: false, error: 'No selector or coordinates provided' };
        }
        break;

      case 'type':
        result = await executeInTab(tabId, 'typeText', {
          text: command.text,
          selector: command.selector
        });
        break;

      case 'navigate':
        if (command.url) {
          await chrome.tabs.update(tabId, { url: command.url });
          result = { success: true };
        } else {
          result = { success: false, error: 'No URL provided' };
        }
        break;

      case 'screenshot':
        result = await captureTabScreenshot(tabId);
        break;

      default:
        result = { success: false, error: 'Unknown command type: ' + type };
    }

    sendWsMessage({
      type: 'result',
      requestId: requestId,
      ...result
    });

  } catch (e) {
    sendWsMessage({
      type: 'result',
      requestId: requestId,
      success: false,
      error: e.message
    });
  }
}

async function executeInTab(tabId, action, params) {
  // Inject scripts if needed
  await chrome.scripting.executeScript({
    target: { tabId: tabId },
    files: ['interaction.js']
  });

  await chrome.scripting.executeScript({
    target: { tabId: tabId },
    files: ['turndown.js']
  });

  await chrome.scripting.executeScript({
    target: { tabId: tabId },
    files: ['content.js']
  });

  // Send message to content script
  return new Promise((resolve, reject) => {
    chrome.tabs.sendMessage(tabId, { action, ...params }, (response) => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
      } else {
        resolve(response);
      }
    });
  });
}

async function captureTabScreenshot(tabId) {
  try {
    // Make sure the tab is active
    await chrome.tabs.update(tabId, { active: true });

    // Wait a moment for tab to be ready
    await sleep(100);

    const dataUrl = await chrome.tabs.captureVisibleTab(null, {
      format: 'jpeg',
      quality: 85
    });

    const base64Data = dataUrl.split(',')[1];
    return { success: true, image: base64Data };
  } catch (e) {
    return { success: false, error: e.message };
  }
}

// ============================================================
// Message Handler (Popup + WebSocket control)
// ============================================================

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  // WebSocket control messages from popup
  if (message.action === 'wsConnect') {
    wsUrl = message.url;
    chrome.storage.sync.set({ wsUrl: wsUrl });
    disconnectWebSocket();
    connectWebSocket();
    sendResponse({ success: true });
    return true;
  }

  if (message.action === 'wsDisconnect') {
    wsUrl = null;
    chrome.storage.sync.remove('wsUrl');
    disconnectWebSocket();
    sendResponse({ success: true });
    return true;
  }

  if (message.action === 'wsStatus') {
    sendResponse({
      connected: ws && ws.readyState === WebSocket.OPEN,
      url: wsUrl
    });
    return true;
  }

  // Original capture functionality
  if (message.action === 'captureFullPage') {
    const captureMode = message.captureMode || 'screenshot';

    if (captureMode === 'text') {
      captureTextMode(message.tabId, message.endpoint, message.textMessage, message.hidden)
        .then(result => sendResponse(result))
        .catch(error => sendResponse({ success: false, error: error.message }));
    } else {
      captureFullPage(message.tabId, message.endpoint, message.textMessage, message.hidden)
        .then(result => sendResponse(result))
        .catch(error => sendResponse({ success: false, error: error.message }));
    }

    // Return true to indicate async response
    return true;
  }
});

async function captureFullPage(tabId, endpoint, textMessage, hidden) {
  try {
    // Inject content script
    await chrome.scripting.executeScript({
      target: { tabId: tabId },
      files: ['content.js']
    });

    // Get page dimensions
    const dimensions = await sendMessageToTab(tabId, { action: 'getPageDimensions' });

    const viewportHeight = dimensions.viewportHeight;
    const viewportWidth = dimensions.viewportWidth;
    const pageHeight = dimensions.pageHeight;
    const pageWidth = dimensions.pageWidth;

    // Calculate number of tiles needed
    const tilesY = Math.ceil(pageHeight / viewportHeight);
    const tilesX = Math.ceil(pageWidth / viewportWidth);
    const totalTiles = tilesY * tilesX;

    console.log(`Capturing ${totalTiles} tiles (${tilesX}x${tilesY})`);

    const tiles = [];
    let tileIndex = 0;

    // Capture tiles row by row
    for (let row = 0; row < tilesY; row++) {
      for (let col = 0; col < tilesX; col++) {
        tileIndex++;

        // Calculate scroll position
        const scrollX = col * viewportWidth;
        const scrollY = row * viewportHeight;

        // Send progress update
        try {
          chrome.runtime.sendMessage({
            action: 'captureProgress',
            current: tileIndex,
            total: totalTiles
          });
        } catch (e) {
          // Popup might be closed, ignore
        }

        // Scroll to position
        await sendMessageToTab(tabId, {
          action: 'scrollToPosition',
          x: scrollX,
          y: scrollY
        });

        // Delay to ensure rendering and respect Chrome's rate limit
        // Chrome limits captureVisibleTab to ~2 calls per second
        await sleep(600);

        // Capture visible tab as JPEG with retry logic
        let dataUrl;
        let retries = 3;
        while (retries > 0) {
          try {
            dataUrl = await chrome.tabs.captureVisibleTab(null, {
              format: 'jpeg',
              quality: 85
            });
            break;
          } catch (error) {
            if (error.message.includes('MAX_CAPTURE_VISIBLE_TAB_CALLS_PER_SECOND')) {
              retries--;
              if (retries > 0) {
                console.log(`Rate limit hit, retrying... (${retries} attempts left)`);
                await sleep(1000); // Wait 1 second before retry
              } else {
                throw new Error('Rate limit exceeded after retries');
              }
            } else {
              throw error;
            }
          }
        }

        // Extract base64 data from data URL
        const base64Data = dataUrl.split(',')[1];

        // Generate text for this tile
        const tileText = textMessage
          ? `${textMessage} [Tile ${tileIndex}/${totalTiles} at ${col},${row}]`
          : `Tile ${tileIndex}/${totalTiles} at ${col},${row}`;

        // Collect tiles for batch sending
        tiles.push({
          text: tileText,
          image: base64Data,
          hidden: hidden
        });
      }
    }

    // Send all tiles at once
    await sendTilesToEndpoint(endpoint, tiles);

    // Reset scroll position
    await sendMessageToTab(tabId, { action: 'resetScroll' });

    return {
      success: true,
      tileCount: totalTiles
    };

  } catch (error) {
    console.error('Capture error:', error);
    throw error;
  }
}

async function captureTextMode(tabId, endpoint, textMessage, hidden) {
  try {
    // Inject Turndown library first, then content script
    await chrome.scripting.executeScript({
      target: { tabId: tabId },
      files: ['turndown.js']
    });

    await chrome.scripting.executeScript({
      target: { tabId: tabId },
      files: ['content.js']
    });

    // Extract page content as markdown
    const result = await sendMessageToTab(tabId, { action: 'extractPageContent' });

    if (!result.success) {
      throw new Error('Failed to extract page content');
    }

    let markdown = result.markdown;

    // Prepend user's text message if provided
    if (textMessage) {
      markdown = `${textMessage}\n\n---\n\n${markdown}`;
    }

    // Send to endpoint as single message
    const payload = [{
      text: markdown,
      hidden: hidden
    }];

    await sendToEndpoint(endpoint, payload);

    return {
      success: true,
      mode: 'text'
    };

  } catch (error) {
    console.error('Text capture error:', error);
    throw error;
  }
}

async function sendToEndpoint(endpoint, payload) {
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
  }

  return response;
}

async function sendTilesToEndpoint(endpoint, tiles) {
  // Send array of tiles to /send-messages endpoint
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(tiles)
  });

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
  }

  return response;
}

function sendMessageToTab(tabId, message) {
  return new Promise((resolve, reject) => {
    chrome.tabs.sendMessage(tabId, message, (response) => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
      } else {
        resolve(response);
      }
    });
  });
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}