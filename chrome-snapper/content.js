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

  else if (message.action === 'extractPageContent') {
    // Clone the document body to avoid modifying the actual page
    const clone = document.body.cloneNode(true);

    // Remove unwanted elements (similar to Shards Markdown.FromHTML SkipTags)
    const skipTags = ['script', 'style', 'nav', 'header', 'footer', 'aside', 'noscript', 'iframe'];
    skipTags.forEach(tag => {
      const elements = clone.querySelectorAll(tag);
      elements.forEach(el => el.remove());
    });

    // Also remove hidden elements and common clutter
    const hiddenSelectors = [
      '[hidden]',
      '[aria-hidden="true"]',
      '.hidden',
      '.sr-only',
      '[style*="display: none"]',
      '[style*="display:none"]'
    ];
    hiddenSelectors.forEach(selector => {
      try {
        clone.querySelectorAll(selector).forEach(el => el.remove());
      } catch (e) {}
    });

    // Convert to markdown using Turndown
    const turndownService = new TurndownService({
      headingStyle: 'atx',
      codeBlockStyle: 'fenced',
      bulletListMarker: '-'
    });

    // Get page title
    const title = document.title || '';

    // Convert HTML to markdown
    let markdown = turndownService.turndown(clone);

    // Prepend title as H1 if available
    if (title) {
      markdown = `# ${title}\n\n${markdown}`;
    }

    // Trim whitespace
    markdown = markdown.trim();

    sendResponse({ success: true, markdown: markdown });
    return true;
  }
});