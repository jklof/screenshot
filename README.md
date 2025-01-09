# Screenshot Tool

A lightweight, customizable screenshot capture tool built with PyQt5. Capture, save, and instantly share screenshots with customizable aspect ratios and multi-monitor support.

## Features

- Global hotkey (Ctrl+Shift+K) for instant screenshot capture
- Customizable aspect ratios (1:1, 4:3, 16:9, 2:3, 3:2, or free-form)
- Multi-monitor support with per-screen capture options
- System tray integration for easy access
- Option to save locally or upload to uguu.se
- Automatic clipboard copy and browser preview of uploaded screenshots
- Draggable selection with Shift key to move the selection area

## Installation

```bash
pip install PyQt5 keyboard requests
```

## Usage

Run the tool with default settings (uploads to uguu.se):
```bash
python grab.py
```

Save screenshots locally instead of uploading:
```bash
python grab.py --save-dir "/path/to/save/directory"
```

### Controls

- **Ctrl+Shift+K**: Start screenshot capture
- **Click and drag**: Select area
- **Shift + drag**: Move selection area
- **Escape**: Cancel capture
- **Right-click tray icon**: Access settings menu

## Requirements

- Python 3.x
- PyQt5
- keyboard
- requests
