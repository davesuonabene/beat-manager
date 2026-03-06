import os
import glob
import json
from datetime import datetime
from typing import List, Tuple

from textual.app import App, ComposeResult, RenderResult
from textual.widgets import (
    Header, Footer, Static, Input, Button, DataTable, 
    Label, TabbedContent, TabPane, Select, ListView, 
    ListItem, TextArea, LoadingIndicator
)
from textual.containers import Horizontal, Vertical, ScrollableContainer, Container
from textual import work, on
from textual.binding import Binding
from textual.message import Message
from textual.reactive import reactive

# Project paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
STATE_JSON = os.path.join(BASE_DIR, "state.json")

from state_manager import StateManager
from video_engine import VideoEngine
from youtube_engine import YouTubeEngine
from audio_engine import AudioEngine

# --- Custom Widgets ---

class Island(Container):
    """A minimalist panel with breathing room."""
    pass

class KeywordManager(Static):
    """Granular keyword manager with group filtering."""
    
    all_keywords = reactive([])
    
    def compose(self) -> ComposeResult:
        with Horizontal(id="kw-filter-strip"):
            yield Label("FILTER:")
            yield Select([
                ("ALL", "ALL"),
                ("PRIMARY", "PRI"),
                ("SECONDARY", "SEC"),
                ("ARTIST", "ART"),
                ("TAGS", "TAG")
            ], id="kw-group-filter", value="ALL")
            
        yield DataTable(id="kw-table", cursor_type="row")
        
        with Horizontal(id="kw-add-strip"):
            yield Select([
                ("PRI", "PRI"),
                ("SEC", "SEC"),
                ("ART", "ART"),
                ("TAG", "TAG")
            ], id="kw-add-group", value="TAG")
            yield Input(placeholder="Add new keyword...", id="kw-add-input")
            yield Button("ADD", id="kw-add-btn", variant="primary")

    def on_mount(self) -> None:
        table = self.query_one("#kw-table", DataTable)
        table.add_columns("GROUP", "KEYWORD", "TREND")
        # Initial dummy data or load from state if implemented
        self.all_keywords = [
            ("PRI", "lo-fi hip hop", "Stable"),
            ("SEC", "chillhop", "Rising"),
            ("ART", "j dilla", "Legendary"),
            ("TAG", "mellow", "High")
        ]

    def watch_all_keywords(self, keywords: list) -> None:
        self.update_table()

    def update_table(self) -> None:
        table = self.query_one("#kw-table", DataTable)
        table.clear()
        filter_val = self.query_one("#kw-group-filter", Select).value
        
        for g, k, t in self.all_keywords:
            if filter_val == "ALL" or g == filter_val:
                table.add_row(g, k.upper(), t)

    @on(Select.Changed, "#kw-group-filter")
    def handle_filter_change(self) -> None:
        self.update_table()

    def add_keyword(self, keyword: str, group: str):
        if not keyword.strip(): return
        new_list = list(self.all_keywords)
        new_list.append((group, keyword.strip().lower(), "NEW"))
        self.all_keywords = new_list
        self.app.notify(f"Added '{keyword}' to {group}", title="Vault Update")

# --- Tabs ---

class ProductionTab(Static):
    def compose(self) -> ComposeResult:
        with Vertical(classes="tab-container"):
            with Island(classes="form-island"):
                yield Label("ASSET CONFIGURATION", classes="section-label")
                yield Label("Audio Source")
                yield Input(placeholder="Path to .wav / .mp3", id="prod-audio", value=os.path.join(BASE_DIR, "dummy_assets/test_beat.mp3"))
                yield Label("Cover Art")
                yield Input(placeholder="Path to .png / .jpg", id="prod-image", value=os.path.join(BASE_DIR, "dummy_assets/test_cover.png"))
                yield Label("Output Path")
                yield Input(placeholder="Render destination...", id="prod-video", value=os.path.join(BASE_DIR, "output.mp4"))
                yield Button("START RENDERING ENGINE", id="btn-render-start", variant="success")

class LibraryTab(Static):
    """Audio library management."""
    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical(id="library-left", classes="island"):
                yield Label("MANAGED FOLDERS", classes="section-label")
                yield DataTable(id="folder-table", cursor_type="row")
                with Horizontal(id="folder-add-strip"):
                    yield Input(placeholder="Path to audio folder...", id="folder-add-input")
                    yield Button("ADD", id="folder-add-btn", variant="primary")
                    yield Button("SCAN FOLDER", id="folder-scan-btn", variant="default")
            
            with Vertical(id="library-right"):
                yield Label("AUDIO FILES", classes="section-label")
                yield DataTable(id="audio-table", cursor_type="row")

    def on_mount(self) -> None:
        ftable = self.query_one("#folder-table", DataTable)
        ftable.add_columns("PATH", "AUDIO COUNT") # Update columns
        
        atable = self.query_one("#audio-table", DataTable)
        atable.add_columns("FILENAME", "TYPE", "DURATION", "SR", "BD", "PATH") # Updated columns
        
        self.audio_engine = AudioEngine() # Initialize AudioEngine FIRST
        self.refresh_folders()

    def refresh_folders(self) -> None:
        ftable = self.query_one("#folder-table", DataTable)
        ftable.clear()
        ftable.add_columns("PATH", "AUDIO COUNT") # Ensure columns are correct
        state = StateManager(STATE_JSON)
        folders = state.get_folders()
        
        for f_doc in folders:
            folder_path = f_doc['path']
            # Get audio count for this folder
            audio_count = self.audio_engine.audio_assets_table.count(Query().parent_folder == folder_path)
            ftable.add_row(folder_path, str(audio_count))

    @on(DataTable.RowSelected, "#folder-table")
    def handle_folder_selected(self, event: DataTable.RowSelected) -> None:
        row_data = self.query_one("#folder-table", DataTable).get_row(event.row_key)
        folder_path = row_data[0] # The path is the first column
        self.load_audio_files(folder_path)

    def load_audio_files(self, path: str) -> None:
        atable = self.query_one("#audio-table", DataTable)
        atable.clear()
        if not os.path.exists(path):
            self.app.notify(f"Folder not found: {path}", severity="error")
            return
            
        # Retrieve scanned assets from the database
        scanned_assets = self.audio_engine.audio_assets_table.search(Query().parent_folder == path)
        if scanned_assets:
            for asset in scanned_assets:
                atable.add_row(
                    asset['filename'],
                    asset['format'].upper(),
                    f"{asset['duration']:.2f}s" if asset['duration'] else "N/A",
                    f"{asset['sample_rate'] / 1000}kHz" if asset['sample_rate'] else "N/A",
                    f"{asset['bit_depth']} bit" if asset['bit_depth'] else "N/A",
                    asset['path']
                )
        else:
            # Fallback to simple file listing if no scanned assets (or not yet scanned)
            patterns = ["*.wav", "*.mp3", "*.aiff", "*.flac"]
            files = []
            for p in patterns:
                files.extend(glob.glob(os.path.join(path, p)))
            
            for f in sorted(files):
                atable.add_row(os.path.basename(f), f.split('.')[-1].upper(), "N/A", "N/A", "N/A", f)
    
    @on(Button.Pressed, "#folder-scan-btn")
    def handle_scan_folder_btn(self) -> None:
        selected_rows = self.query_one("#folder-table", DataTable).selected_row_keys
        if not selected_rows:
            self.app.notify("Please select a folder to scan", severity="warning")
            return
        
        # Assuming single selection, get the path from the first selected row
        row_key = list(selected_rows)[0]
        row_data = self.query_one("#folder-table", DataTable).get_row(row_key)
        folder_path = row_data[0]

        self.app.notify(f"Starting scan for {os.path.basename(folder_path)}...", timeout=5)
        self.run_scan_folder(folder_path)

    @work(exclusive=True, thread=True)
    def run_scan_folder(self, path: str) -> None:
        try:
            self.audio_engine.scan_folder(path)
            self.app.call_from_thread(self.app.notify, f"Scan complete for {os.path.basename(path)}", title="Audio Engine")
            self.app.call_from_thread(self.query_one(LibraryTab).refresh_folders) # Refresh folder list to update counts
            self.app.call_from_thread(self.query_one(LibraryTab).load_audio_files, path) # Refresh audio list
        except Exception as e:
            self.app.call_from_thread(self.app.notify, f"Scan failed for {os.path.basename(path)}: {e}", severity="error")

class BrandingTab(Static):
    """Keywords as protagonists + Report Viewer."""
    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical(id="branding-left"):
                yield Label("KEYWORD VAULT", classes="section-label")
                yield KeywordManager()
            
            with Vertical(id="branding-right"):
                yield Label("STRATEGY REPORT VIEWER", classes="section-label")
                with Island():
                    yield TextArea(id="branding-report-viewer", read_only=True)
                    with Horizontal(classes="viewer-footer"):
                        yield Button("REFRESH REPORTS", id="btn-refresh-reports")
                        yield Label("Press 'K' to harvest highlighted text", classes="hint-text")

class ResearchTab(Static):
    """Niche scans and target parameterization."""
    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical(id="research-controls", classes="island"):
                yield Label("SCAN PARAMETERS", classes="section-label")
                yield Label("Target Group")
                yield Select([
                    ("PRIMARY", "PRI"),
                    ("SECONDARY", "SEC"),
                    ("ARTIST", "ART"),
                    ("TAGS", "TAG")
                ], id="res-scan-group", value="PRI")
                yield Label("Seed Keyword")
                yield Input(placeholder="e.g. phonk", id="res-scan-query")
                yield Button("LAUNCH NICHE DISCOVERY", id="btn-niche-scan", variant="primary")
                
                yield Label("RECENT REPORTS", classes="section-label", id="reports-list-label")
                yield ListView(id="res-report-list")

            with Vertical(id="research-display"):
                yield Label("ANALYSIS TERMINAL", classes="section-label")
                yield TextArea(id="research-report-viewer", read_only=True)

class YoutubeTab(Static):
    """Sub-tabs for Upload, Branding, Research? Requirement says YOUTUBE is main tab, others are sub-tabs."""
    def compose(self) -> ComposeResult:
        with TabbedContent(initial="upload"):
            with TabPane("UPLOAD", id="upload"):
                with Island(classes="form-island"):
                    yield Label("METADATA & PUBLISHING", classes="section-label")
                    yield Label("Video File")
                    yield Input(placeholder="Path to .mp4", id="yt-video", value=os.path.join(BASE_DIR, "output.mp4"))
                    yield Label("Title")
                    yield Input(placeholder="Catchy title...", id="yt-title")
                    yield Label("Description")
                    yield TextArea(id="yt-desc", classes="small-text-area")
                    
                    with Horizontal(classes="multi-input-row"):
                        with Vertical():
                            yield Label("Category")
                            yield Select([("Music", "10"), ("Entertainment", "24")], id="yt-cat", value="10")
                        with Vertical():
                            yield Label("Privacy")
                            yield Select([("Private", "private"), ("Public", "public")], id="yt-privacy", value="private")
                    
                    yield Button("QUEUE UPLOAD", id="btn-yt-upload", variant="primary")
            
            with TabPane("BRANDING", id="branding"):
                yield BrandingTab()
            
            with TabPane("RESEARCH", id="research"):
                yield ResearchTab()

class QueuePanel(Static):
    def compose(self) -> ComposeResult:
        yield Label("SYSTEM QUEUE", classes="section-label")
        yield DataTable(id="queue-table")

    def on_mount(self) -> None:
        table = self.query_one("#queue-table", DataTable)
        table.add_columns("ID", "TYPE", "TARGET", "STATUS")
        self.set_interval(2.0, self.update_queue)

    def update_queue(self) -> None:
        try:
            table = self.query_one("#queue-table", DataTable)
            table.clear()
            state = StateManager(STATE_JSON)
            for task in state.get_tasks():
                table.add_row(
                    f"#{task.doc_id}", 
                    task['type'], 
                    os.path.basename(task['target']), 
                    task['status'].upper()
                )
        except: pass

# --- Main App ---

class BeatManagerApp(App):
    TITLE = "BEAT MANAGER PRO"
    CSS = """
    Screen { background: #080808; color: #e0e0e0; }
    
    Header { background: #111; color: #00ff00; text-style: bold; border-bottom: solid #222; }
    Footer { background: #111; color: #888; border-top: solid #222; }
    
    TabbedContent { height: 1fr; }
    TabPane { padding: 0; background: transparent; }
    
    Island {
        background: #121212;
        border: none;
        padding: 1 2;
        margin: 1;
    }
    
    .form-island {
        max-width: 80;
        align-horizontal: center;
    }
    
    .section-label {
        color: #555;
        text-style: bold;
        margin: 1 0;
    }
    
    Label { margin-top: 1; color: #aaa; }
    Input { 
        background: #1a1a1a; 
        border: none; 
        color: #fff; 
        padding: 0 1;
        margin-bottom: 1;
    }
    Input:focus { background: #222; border-left: solid #00ff00; }
    
    Select { background: #1a1a1a; border: none; margin-bottom: 1; }
    
    Button {
        margin: 1 0;
        border: none;
        background: #222;
        color: #ccc;
    }
    Button:hover { background: #333; color: #fff; }
    Button.-variant-primary { background: #004488; }
    Button.-variant-success { background: #006622; }
    
    DataTable { 
        background: transparent; 
        border: none; 
        height: 1fr;
    }
    DataTable > .datatable--header { background: #111; color: #00ff00; }
    
    #queue-panel {
        height: 10;
        background: #0a0a0a;
        border-top: solid #222;
        padding: 0 2;
    }
    
    /* Branding layout */
    #branding-left { width: 45%; }
    #branding-right { width: 55%; }
    #branding-report-viewer { height: 1fr; background: #0a0a0a; border: none; }
    .viewer-footer { height: 3; align: right middle; }
    .hint-text { color: #444; text-style: italic; margin-left: 2; }
    
    /* Research layout */
    #research-controls { width: 35%; height: 100%; }
    #research-display { width: 65%; height: 100%; }
    #res-report-list { height: 1fr; background: #0a0a0a; margin: 1 0; }
    #research-report-viewer { height: 1fr; background: #0a0a0a; border: none; }
    
    /* Library layout */
    #library-left { width: 35%; }
    #library-right { width: 65%; }
    #folder-table { height: 1fr; }
    #audio-table { height: 1fr; }
    
    .multi-input-row { height: auto; }
    .multi-input-row > Vertical { padding: 0 1; }
    
    .small-text-area { height: 6; background: #1a1a1a; border: none; }
    
    ListItem { padding: 0 1; color: #888; }
    ListItem:hover { background: #1a1a1a; color: #fff; }
    ListItem.--highlight { background: #222; color: #00ff00; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("r", "refresh_all", "Refresh UI", show=True),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            with TabPane("PRODUCTION"):
                yield ProductionTab()
            with TabPane("LIBRARY"):
                yield LibraryTab()
            with TabPane("YOUTUBE"):
                yield YoutubeTab()
        yield QueuePanel(id="queue-panel")
        yield Footer()

    def on_mount(self) -> None:
        # Initialize state
        state = StateManager(STATE_JSON)

    def action_refresh_all(self) -> None:
        self.query_one(LibraryTab).refresh_folders()
        self.notify("UI Refreshed", title="System")

    @on(Button.Pressed, "#folder-add-btn")
    def handle_folder_add(self) -> None:
        path = self.query_one("#folder-add-input", Input).value
        if path and os.path.exists(path):
            StateManager(STATE_JSON).add_folder(path)
            self.query_one(LibraryTab).refresh_folders()
            self.query_one("#folder-add-input", Input).value = ""
            self.notify(f"Added folder: {os.path.basename(path)}")
        else:
            self.notify("Invalid folder path", severity="error")

    # --- Engine Actions ---

    @on(Button.Pressed, "#btn-render-start")
    def handle_render(self) -> None:
        audio = self.query_one("#prod-audio", Input).value
        image = self.query_one("#prod-image", Input).value
        output = self.query_one("#prod-video", Input).value
        
        StateManager(STATE_JSON).add_task("RENDER", output, "Pending", audio=audio, image=image)
        self.notify(f"Rendering Task Queued: {os.path.basename(output)}")

    @on(Button.Pressed, "#btn-yt-upload")
    def handle_yt_upload(self) -> None:
        video = self.query_one("#yt-video", Input).value
        title = self.query_one("#yt-title", Input).value
        description = self.query_one("#yt-desc", TextArea).text
        category = self.query_one("#yt-cat", Select).value
        privacy = self.query_one("#yt-privacy", Select).value
        
        StateManager(STATE_JSON).add_task(
            "UPLOAD", 
            title, 
            "Pending", 
            video=video, 
            description=description, 
            category=category, 
            privacy=privacy,
            channel="default_channel"
        )
        self.notify(f"Upload Task Queued: {title}")


if __name__ == "__main__":
    app = BeatManagerApp()
    app.run()
