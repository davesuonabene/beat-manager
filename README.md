# BeatManager

BeatManager is a professional "Type Beat" channel management system designed for high-performance video rendering, YouTube automation, and Obsidian-integrated asset management. It features a modern TUI (Terminal User Interface) and a robust multi-threaded background worker powered by HTDemucs.

## 🏗️ Architecture & Development

BeatManager follows a **Modular Service-Oriented Architecture** with a **Markdown-Master** philosophy. Every audio asset is linked to a primary Markdown file in a unified library map.

### Project Structure
```text
beat-manager/
├── app/
│   ├── core/               # ENGINE LAYER: Pure logic engines.
│   │   ├── video_engine.py    # FFmpeg wrappers (Pure)
│   │   ├── youtube_engine.py  # Google API calls (Pure)
│   │   ├── state_manager.py   # SQLite abstractions (Thread-safe)
│   │   ├── audio_engine.py    # Metadata extraction (mutagen)
│   │   ├── stems_engine.py    # HTDemucs source separation
│   │   └── library_manager_engine.py # Filesystem/Obsidian Sync
│   ├── models/             # SCHEMAS: Type safety across the project.
│   │   └── schemas.py         # Pydantic models for configs and assets
│   └── services/           # SERVICE LAYER: Business logic & Coordination.
│       ├── dispatcher.py      # Main entry point for executing tasks
│       └── strategy_manager.py# Planning and scheduling
├── assets/library/         # CENTRAL REPOSITORY
│   ├── audio/              # WAV/MP3 files (Originals/Raw)
│   ├── md/                 # Markdown Master files (Obsidian Vault)
│   └── stems/              # ST-prefixed separation folders
├── cli.py                  # CLI Interface (Automation Engine)
├── tui.py                  # Terminal UI Dashboard (Management)
└── state.db                # Central SQLite state
```

### Development Principles
1.  **Markdown-Master**: The database index is rebuilt from the `md/` folder. Every asset MUST have a corresponding `.md` file with YAML frontmatter.
2.  **Thread Safety**: `StateManager` uses `check_same_thread=False` to allow concurrent TUI and background worker access.
3.  **ST Naming**: Stems are stored in folders prefixed with `ST` + the parent Asset ID for instant discovery.
4.  **Interface Parity**: Every engine feature must be exposed in both TUI and `cli.py`.

---

## 🛠️ CLI & Robustness

The CLI is the automation engine. It includes diagnostic tools to ensure the complex environment is always healthy.

### Core Commands
-   `python3 cli.py doctor`: Checks FFmpeg, Demucs, PyTorch, and DB integrity.
-   `python3 cli.py stems --id <id>`: Manually trigger high-quality stem separation.
-   `python3 cli.py render`: immediate FFmpeg video composition.
-   `python3 cli.py status`: View the SQLite task queue.

---

## 🚀 Getting Started

### Prerequisites
-   **FFmpeg**: For video and audio processing.
-   **Python 3.10+**
-   **Torch & Torchcodec**: For AI-powered stems separation.
-   **HTDemucs**: Installed within the local virtual environment.
-   **tmux**: Required for the `beatmgr` management script.

### Installation
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
# Check your environment
python3 cli.py doctor
```

---

## 🕹️ Management & Remote Export

### The `mmpy` Command
The project includes a "plug-and-play" management script linked to `mmpy`.
- **`mmpy`**: (or `mmpy attach`) Automatically starts the app in a tmux session if not running and attaches to it.
- **`mmpy stop`**: Safely kills the tmux session.
- **`mmpy status`**: Checks if the manager is running.
- **`mmpy restart`**: Performs a clean restart.

This script ensures the TUI remains running even if your SSH connection drops.

### "Send to Remote" (SCP)
When connected via SSH, the **Export Modal** (triggered with `E` in the TUI) features a **"SEND TO REMOTE"** button.
- **Automatic Detection**: It detects your client machine's IP address.
- **One-Click Transfer**: Exports the assets to a temp folder and pushes them via `scp` to your local `~/Downloads` folder.
- **Reactive UI**: The button is greyed out if no connection is detected and enables itself automatically once you connect.
- **Multi-session support**: The `mmpy` command synchronizes your latest SSH environment with the running TUI every time you attach.

---

## 🛠️ Operating the System

### 1. The Dashboard (TUI)
Features **Multi-Version Selector** at the bottom right. Instantly switch between Raw audio, Mastered versions, and separated Stems during playback. Supports **Bulk Tagging** using the `*` placeholder logic.
```bash
./venv/bin/python3 tui.py
```

### 2. Obsidian Integration
Point your Obsidian vault to `assets/library/`. The `md/` folder provides a complete, linked knowledge graph of your library with automatic `[[audio]]` back-links.

### 3. Background Worker
Processes heavy tasks like `RENDER` and `STEMS` without blocking the UI.
-   **Start:** `nohup ./venv/bin/python3 worker.py > worker.log 2>&1 &`

---

## 📊 Achievements & Milestones

### 🏆 Milestone: Master Software Upgrade
-   **HTDemucs Integration**: Seamlessly deconstruct any track into Vocals, Drums, Bass, and Other.
-   **SONG Asset Type**: Dedicated workflow for full track management.
-   **Tag-based Organization**: Full replacement of the legacy "Collection" system with high-speed tagging.
-   **SQLite Concurrency**: Multi-threaded database access for simultaneous UI and processing.
-   **RECORDING Asset Type**: Dedicated workflow for live recorded audio tracks.
-   **Deep Library Sync**: Automatic 1:1 mapping of 2,400+ physical assets to Markdown files.

---

## 🛠 Next Steps
*   **Version History**: Automatic tracking of mix iterations within the Markdown file.
*   **Stems Metadata**: AI-powered auto-tagging of stems (e.g., detecting loop key/bpm).
*   **Agent API**: Exposing `dispatcher.py` as a toolset for autonomous AI agents.
