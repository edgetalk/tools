# edge talk Snapper

A Chrome extension that captures full-page screenshots by tiling and sends them to an edge talk server using batch mode.

## Features

- Captures full-page screenshots including content beyond the viewport
- Automatically scrolls and captures tiles
- Sends all tiles in a single batch HTTP POST request
- JPEG compression for efficient transfer (quality: 85%)
- Optional text message and hidden flag
- Simple popup UI for configuration and triggering captures
- Settings persist across sessions

## Installation

1. Open Chrome and navigate to `chrome://extensions/`
2. Enable "Developer mode" (toggle in top-right corner)
3. Click "Load unpacked"
4. Select the `chrome-snapper` directory
5. The extension icon should appear in your toolbar

## Usage

1. Click the edge talk Snapper extension icon in your toolbar
2. Enter your server address (e.g., `http://192.168.50.166:33053`)
3. Optionally enter a text message
4. Optionally check "Hidden message" to mark tiles as hidden
5. Click "Capture & Send"
6. The extension will:
   - Scroll through the entire page
   - Capture tiles of the visible viewport as JPEG images
   - Send all tiles at once to `{server}/send-messages`

## Protocol: edge talk Format

The extension automatically appends `/send-messages` to your server address and sends a JSON array of tiles:

```json
[
  {
    "text": "Your message [Tile 1/6 at 0,0]",
    "image": "base64-encoded JPEG data...",
    "hidden": false
  },
  {
    "text": "Your message [Tile 2/6 at 1,0]",
    "image": "base64-encoded JPEG data...",
    "hidden": false
  }
  ...
]
```

Each tile includes:
- `text`: Your custom message plus tile metadata (index, position)
- `image`: Base64-encoded JPEG image
- `hidden`: Boolean flag for hidden messages

## Server Requirements

Your server must implement a `/send-messages` endpoint that:
- Accepts `POST` requests with `Content-Type: application/json`
- Receives a JSON array of tile objects
- Each tile contains `text`, `image` (base64 JPEG), and `hidden` fields

See `/Users/sugar/devel/Soul-mender/Scripts-Src/send-server.shs` for the reference implementation.

## Technical Details

- Uses Chrome Manifest V3
- Captures visible tab using `chrome.tabs.captureVisibleTab()` with JPEG format
- Tiles are captured row-by-row, left-to-right
- All tiles are collected in memory, then sent in a single batch request
- JPEG quality: 85%
- Scroll position is reset after capture completes
- 600ms delay between captures to respect Chrome's rate limit (~2 captures/second)
- Automatic retry with 1-second backoff if rate limit is hit

## Permissions

- `activeTab`: Capture the current tab
- `scripting`: Inject content script for scrolling
- `storage`: Save server address, text message, and hidden flag
- `tabs`: Access tab information
- `<all_urls>`: Send HTTP requests to any endpoint

## Notes

- All tiles are sent in a single HTTP request for efficiency
- Very long pages will generate many tiles (larger payload)
- Network errors will stop the capture process
- Settings are saved in Chrome sync storage and persist across browser sessions
- The extension works with the edge talk server protocol