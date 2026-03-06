# BeatManager

BeatManager is a "Type Beat" channel management system designed for high-performance video rendering, YouTube automation, and SEO-driven niche analysis. It features a TUI (Terminal User Interface) for monitoring and a background worker for autonomous task execution.

## 🚀 Getting Started

### Prerequisites
- **FFmpeg**: Required for video rendering.
- **Python 3.10+**: Recommended version.
- **Google Cloud Console Credentials**: `client_secrets.json` is required for YouTube uploads.

### Installation
1.  **Create Virtual Environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```

## 🛠️ Operating the System

### 1. The TUI (Interface)
Launch the TUI to manage audio assets, queue renders, and monitor the upload status:
```bash
./venv/bin/python3 tui.py
```
*Note: If you are on i3, you can use the status bar icon or the `$mod+Ctrl+b` shortcut.*

### 2. The Worker (Background Execution)
The worker processes all tasks (RENDER, UPLOAD) from the queue. It must be running for any "Pending" tasks to complete.

#### **Control Commands**
- **Start Worker (Background):**
  ```bash
  nohup ./venv/bin/python3 worker.py > worker.log 2>&1 &
  ```
- **Stop Worker:**
  ```bash
  pkill -f worker.py
  ```
- **Check if Running:**
  ```bash
  pgrep -af worker.py
  ```
- **Monitor Logs:**
  ```bash
  tail -f worker.log
  ```

## 🖥️ i3 Integration

BeatManager is integrated into the i3 environment:
- **Shortcut:** `$mod+Ctrl+b` launches the TUI.
- **Status Bar:** Click the green ** BeatManager** icon in the top bar.
- **Autostart:** The worker is configured to start automatically on login in `~/.config/i3/config`.

## 🏗️ Architecture
The project follows a decoupled **Worker-Queue** architecture:
1.  **TUI/Agents:** Add tasks to `state.json`.
2.  **Worker:** Polls `state.json` and executes engines (FFmpeg, YouTube API).
3.  **State:** Centralized persistence using TinyDB.

For more technical details, see [ARCHITECTURE.md](./ARCHITECTURE.md).
