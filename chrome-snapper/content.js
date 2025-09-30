// Content script for page scrolling and dimension reporting

// Listen for messages from background script
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'getPageDimensions') {
    // Get full page dimensions and viewport size
    const dimensions = {
      pageWidth: Math.max(
        document.documentElement.scrollWidth,
        document.body.scrollWidth
      ),
      pageHeight: Math.max(
        document.documentElement.scrollHeight,
        document.body.scrollHeight
      ),
      viewportWidth: window.innerWidth,
      viewportHeight: window.innerHeight,
      devicePixelRatio: window.devicePixelRatio || 1
    };
    sendResponse(dimensions);
  }

  else if (message.action === 'scrollToPosition') {
    // Scroll to specified position
    window.scrollTo({
      left: message.x || 0,
      top: message.y || 0,
      behavior: 'instant'
    });

    // Wait a bit for rendering to settle, then confirm
    setTimeout(() => {
      sendResponse({
        success: true,
        scrollX: window.scrollX,
        scrollY: window.scrollY
      });
    }, 100);

    // Return true to indicate we'll send response asynchronously
    return true;
  }

  else if (message.action === 'resetScroll') {
    // Scroll back to top
    window.scrollTo({
      left: 0,
      top: 0,
      behavior: 'instant'
    });

    setTimeout(() => {
      sendResponse({ success: true });
    }, 100);

    return true;
  }
});