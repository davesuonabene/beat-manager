# BeatManager

BeatManager is a professional "Type Beat" channel management system designed for high-performance video rendering, YouTube automation, and SEO-driven niche management. It features a modern TUI (Terminal User Interface) for management and a robust background worker for autonomous task execution.

## 🏗️ Architecture & Development

BeatManager follows a **Modular Service-Oriented Architecture**. To maintain a robust system, follow the established patterns when adding features.

### Project Structure
```text
beat-manager/
├── app/
│   ├── core/               # LOW-LEVEL: Pure logic engines. No business rules here.
│   │   ├── video_engine.py    # FFmpeg wrappers (Pure)
│   │   ├── youtube_engine.py  # Google API calls (Pure)
│   │   ├── state_manager.py   # SQLite abstractions (Persistence)
│   │   ├── audio_engine.py    # Metadata extraction (mutagen)
│   │   └── library_manager_engine.py # Filesystem/DB sync for assets
│   ├── models/             # SCHEMAS: Type safety across the project.
│   │   └── schemas.py         # Pydantic models for configs and assets
│   └── services/           # HIGH-LEVEL: Business logic & Coordination.
│       ├── dispatcher.py      # Main entry point for executing tasks
│       └── strategy_manager.py# Planning, queueing, and scheduling
├── data/                   # Strategy and Plan configurations (JSON)
├── cli.py                  # CLI Interface (Target: 100% feature parity)
├── tui.py                  # Terminal UI Dashboard (Textual)
├── worker.py               # Background task processor
└── state.db                # Central SQLite state
```

### How to Work on the Code
1.  **Schema First**: If adding a new asset type or configuration, start in `app/models/schemas.py`.
2.  **Engine Logic**: Put pure, stateless logic (like calling a new API or tool) in `app/core/`. Engines should not know about the TUI or CLI.
3.  **Persistence**: Use `StateManager` in `app/core/state_manager.py` for all DB operations. Do not write raw SQL in other modules.
4.  **Service Layer**: Use `TaskDispatcher` to coordinate multiple engines. This is where you handle task registration, status updates, and logging.
5.  **Interface Parity**: Every feature added to the TUI **must** also be accessible via `cli.py`.

---

## 🛠️ CLI Robustness & Parity

The CLI is designed to be the "Engine Room" of the project. Current focus is on making it 100% robust for automation.

### Current CLI Features
-   `status`: Check the SQLite task queue.
-   `render`: Trigger immediate FFmpeg video composition.
-   `upload`: Push a video to YouTube with specified metadata.
-   `queue`: List or activate items from the weekly plan.
-   `process`: Run pending tasks manually (useful for debugging).

### 🚀 Upcoming CLI Improvements (Roadmap)
-   [ ] **Asset Management**: Add `cli.py library list/tag/edit` to allow bulk metadata editing via CLI (matching new TUI features).
-   [ ] **Import/Export**: Add `cli.py import --path <dir>` to automate library expansion without the TUI.
-   [ ] **Dry Runs**: Implement `--dry-run` for `render` and `upload` to validate paths and credentials before execution.
-   [ ] **JSON Output**: Add `--json` flag to all commands for easier integration with external scripts (e.g., `jq`).
-   [ ] **Enhanced Logging**: Implement consistent verbosity levels (`-v`, `-vv`) across all commands.
-   [ ] **Health Checks**: Add `cli.py doctor` to verify FFmpeg installation, SQLite integrity, and YouTube API credentials.

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
- **Autostart:** The worker is designed to run as a persistent background process.

---

## 🛠 Next Steps & Integration

BeatManager is moving toward a role as an **agnostic publishing tool** for high-level orchestrators.

*   **PydanticAI Routines**: Integration of PydanticAI to handle complex decision-making for rendering and YouTube metadata generation locally.
*   **Agnostic Functions**: Exposing core rendering and upload flows as decoupled functions that can be called by external agents.
*   **Mission Control Integration**: Chrono will act as the master **Mission Control**, wrapping BeatManager's functions into **Prefect tasks** to execute end-to-end beat selling strategies.

