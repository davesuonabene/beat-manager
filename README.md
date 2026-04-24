# BeatManager

BeatManager is a professional "Type Beat" channel management system designed for high-performance video rendering, YouTube automation, and SEO-driven niche management. It features a modern TUI (Terminal User Interface) for management and a robust background worker for autonomous task execution.

## 🏗️ Architecture

BeatManager follows a **Modular Service-Oriented Architecture** with a decoupled **Worker-Queue** model, now upgraded to a robust **SQLite** backend.

### Project Structure
```text
beat-manager/
├── app/
│   ├── core/               # Low-level execution engines
│   │   ├── video_engine.py    # FFmpeg-based video composition
│   │   ├── youtube_engine.py  # Google API-based upload manager
│   │   ├── state_manager.py   # SQLite state & persistence layer (Migrated from TinyDB)
│   │   └── audio_engine.py    # Audio metadata & asset indexing
│   ├── models/             # Data schemas and types
│   │   └── schemas.py         # Pydantic-based configuration models
│   └── services/           # High-level business logic
│       ├── dispatcher.py      # Orchestrates engines and state
│       └── strategy_manager.py# Handles planning and queueing
├── assets/                 # Storage for audio and image assets
├── data/                   # Strategy, plans, and queue JSON files
├── cli.py                  # Command-line interface
├── tui.py                  # Textual-based terminal dashboard
├── worker.py               # Background task processor
└── state.db                # Centralized SQLite database (Concurrent-safe)
```

### Core Components
1.  **State Layer (`state_manager.py`):** Centralized repository using **SQLite**. Replaces the legacy TinyDB implementation to provide row-level locking and prevent data corruption during concurrent task execution.
2.  **Execution Engines:**
    -   **Video Engine:** High-quality H.264 encoding via FFmpeg (1080p).
    -   **YouTube Engine:** Secure OAuth2 uploads with scheduling and automated metadata mapping.
    -   **Audio Engine:** Automated scanning and metadata extraction for Suno and local assets.
3.  **Dispatcher (`dispatcher.py`):** The bridge between interfaces and core logic. Manages task lifecycle with improved concurrency handling.
4.  **Strategy Manager (`strategy_manager.py`):** Automates the creation of weekly upload plans based on user-defined niches and preferences.

---

## 🚀 Getting Started

### Prerequisites
-   **FFmpeg**: Required for video rendering.
-   **Python 3.10+**
-   **Google Cloud Credentials**: `client_secrets.json` in the root for YouTube API access.

### Installation
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## 🛠️ Operating the System

### 1. The Dashboard (TUI)
Manage assets, queue renders, and monitor activity in real-time. The TUI is optimized for the new SQLite backend:
```bash
./venv/bin/python3 tui.py
```

### 2. The Worker (Background Execution)
The worker processes the task queue. SQLite ensures the worker and TUI can interact with the state simultaneously.
-   **Start:** `nohup ./venv/bin/python3 worker.py > worker.log 2>&1 &`
-   **Stop:** `pkill -f worker.py`

### 3. CLI Tool
Direct access to engine functions:
-   `python3 cli.py status`: View current task queue.
-   `python3 cli.py render --audio <path> --image <path>`: Manual render.
-   `python3 cli.py upload --video <path> --title "..."`: Manual YouTube upload.

---

## 📊 Project Status & Achievements

### Recent Milestones
-   **SQLite Migration:** Successfully migrated 2,400+ library assets from TinyDB to SQLite to support high-concurrency operations.
-   **Project 'typebeatssuck':** Completed the first phase of automated YouTube publishing, including sequential rendering and scheduled uploading of experimental assets.
-   **TUI Stability:** Refactored TUI engine initialization to prevent race conditions during startup.

### In Development
-   **SEO Analytics Engine:** Real-time tracking of YouTube performance data.
-   **Automated LLM Metadata:** Integration with Gemini/GPT for context-aware titles and descriptions.

---

## 🖥️ System Integration (i3/Linux)
-   **Shortcut:** `$mod+Ctrl+b` launches the TUI.
-   **Status Bar:** Integrates with polybar/i3status for real-time monitoring.
-   **Autostart:** The worker is designed to run as a persistent background process.
