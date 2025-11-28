// Interaction scripts for web automation
// Ported from WebViewInteractionShard.swift

const InteractionScripts = {
  // Get all interactive elements on the page
  getInteractiveElements: function() {
    const elements = [];
    const seen = new Set();

    // Selectors for interactive elements
    const interactiveSelectors = [
      'a[href]',
      'button',
      'input',
      'textarea',
      'select',
      '[role="button"]',
      '[role="link"]',
      '[role="menuitem"]',
      '[role="tab"]',
      '[onclick]',
      '[tabindex]:not([tabindex="-1"])',
      'summary',
      'details',
      '[contenteditable="true"]'
    ];

    // Helper to generate a unique selector for an element
    function getSelector(el) {
      if (el.id) {
        return '#' + CSS.escape(el.id);
      }

      // Try to build a unique selector
      let selector = el.tagName.toLowerCase();

      if (el.className && typeof el.className === 'string') {
        const classes = el.className.trim().split(/\s+/).filter(c => c.length > 0);
        if (classes.length > 0) {
          selector += '.' + classes.map(c => CSS.escape(c)).join('.');
        }
      }

      // Add attributes for inputs
      if (el.name) {
        selector += '[name="' + CSS.escape(el.name) + '"]';
      }
      if (el.type && el.tagName.toLowerCase() === 'input') {
        selector += '[type="' + CSS.escape(el.type) + '"]';
      }

      // Check if this selector is unique
      const matches = document.querySelectorAll(selector);
      if (matches.length === 1) {
        return selector;
      }

      // Add nth-child if needed
      const parent = el.parentElement;
      if (parent) {
        const siblings = Array.from(parent.children);
        const index = siblings.indexOf(el) + 1;
        selector += ':nth-child(' + index + ')';
      }

      return selector;
    }

    // Helper to get visible text
    function getVisibleText(el) {
      // For inputs, get placeholder or value
      if (el.tagName.toLowerCase() === 'input') {
        return el.placeholder || el.value || el.getAttribute('aria-label') || '';
      }
      if (el.tagName.toLowerCase() === 'textarea') {
        return el.placeholder || '';
      }

      // Get aria-label first
      const ariaLabel = el.getAttribute('aria-label');
      if (ariaLabel) return ariaLabel;

      // Get text content, but limit length
      const text = el.innerText || el.textContent || '';
      return text.trim().substring(0, 100);
    }

    // Helper to determine element type
    function getElementType(el) {
      const tag = el.tagName.toLowerCase();
      const role = el.getAttribute('role');

      if (role === 'button' || tag === 'button') return 'button';
      if (role === 'link' || tag === 'a') return 'link';
      if (tag === 'input') {
        const type = el.type || 'text';
        if (type === 'submit' || type === 'button') return 'button';
        if (type === 'checkbox') return 'checkbox';
        if (type === 'radio') return 'radio';
        return 'input';
      }
      if (tag === 'textarea') return 'textarea';
      if (tag === 'select') return 'select';
      if (role === 'menuitem') return 'menuitem';
      if (role === 'tab') return 'tab';
      if (el.getAttribute('contenteditable') === 'true') return 'editable';

      return 'clickable';
    }

    // Query all interactive elements
    const allElements = document.querySelectorAll(interactiveSelectors.join(', '));

    allElements.forEach(el => {
      // Skip hidden elements
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return;

      const style = window.getComputedStyle(el);
      if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return;

      // Skip if not in viewport (with some margin)
      if (rect.bottom < -100 || rect.top > window.innerHeight + 100) return;
      if (rect.right < -100 || rect.left > window.innerWidth + 100) return;

      const selector = getSelector(el);

      // Skip duplicates
      if (seen.has(selector)) return;
      seen.add(selector);

      elements.push({
        type: getElementType(el),
        selector: selector,
        text: getVisibleText(el),
        x: Math.round(rect.x),
        y: Math.round(rect.y),
        width: Math.round(rect.width),
        height: Math.round(rect.height),
        tag: el.tagName.toLowerCase(),
        href: el.href || null,
        disabled: el.disabled || false
      });
    });

    return elements;
  },

  // Click element by selector
  clickBySelector: function(selector) {
    const el = document.querySelector(selector);
    if (!el) {
      return { success: false, error: 'Element not found: ' + selector };
    }

    // Scroll element into view
    el.scrollIntoView({ behavior: 'instant', block: 'center' });

    // Focus the element
    el.focus();

    // Dispatch click event
    const clickEvent = new MouseEvent('click', {
      bubbles: true,
      cancelable: true,
      view: window
    });
    el.dispatchEvent(clickEvent);

    return { success: true };
  },

  // Click element by coordinates
  clickByCoordinates: function(x, y) {
    const el = document.elementFromPoint(x, y);
    if (!el) {
      return { success: false, error: 'No element at coordinates (' + x + ', ' + y + ')' };
    }

    // Focus the element
    el.focus();

    // Dispatch click event
    const clickEvent = new MouseEvent('click', {
      bubbles: true,
      cancelable: true,
      view: window,
      clientX: x,
      clientY: y
    });
    el.dispatchEvent(clickEvent);

    return { success: true, tag: el.tagName.toLowerCase() };
  },

  // Type text into element
  typeText: function(text, selector) {
    let el;

    if (selector) {
      el = document.querySelector(selector);
      if (!el) {
        return { success: false, error: 'Element not found: ' + selector };
      }
    } else {
      el = document.activeElement;
      if (!el || el === document.body) {
        return { success: false, error: 'No element is focused' };
      }
    }

    // Focus the element
    el.focus();

    // Clear existing value if it's an input/textarea
    if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
      el.value = '';
    }

    // Type each character
    for (const char of text) {
      const keydownEvent = new KeyboardEvent('keydown', { key: char, bubbles: true });
      const keypressEvent = new KeyboardEvent('keypress', { key: char, bubbles: true });
      const inputEvent = new InputEvent('input', { data: char, bubbles: true });
      const keyupEvent = new KeyboardEvent('keyup', { key: char, bubbles: true });

      el.dispatchEvent(keydownEvent);
      el.dispatchEvent(keypressEvent);

      if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
        el.value += char;
      } else if (el.isContentEditable) {
        document.execCommand('insertText', false, char);
      }

      el.dispatchEvent(inputEvent);
      el.dispatchEvent(keyupEvent);
    }

    // Dispatch change event
    el.dispatchEvent(new Event('change', { bubbles: true }));

    return { success: true };
  }
};

// Make available globally for content script
if (typeof window !== 'undefined') {
  window.InteractionScripts = InteractionScripts;
}
