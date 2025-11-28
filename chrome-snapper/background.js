// Background service worker for capture orchestration

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
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