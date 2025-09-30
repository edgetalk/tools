// Background service worker for capture orchestration

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'captureFullPage') {
    captureFullPage(message.tabId, message.endpoint, message.textMessage, message.hidden)
      .then(result => sendResponse(result))
      .catch(error => sendResponse({ success: false, error: error.message }));

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

        // Small delay to ensure rendering
        await sleep(150);

        // Capture visible tab as JPEG
        const dataUrl = await chrome.tabs.captureVisibleTab(null, {
          format: 'jpeg',
          quality: 85
        });

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