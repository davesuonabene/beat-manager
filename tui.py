import os
import glob
import json
import time
from datetime import datetime
from typing import List, Tuple

from textual.app import App, ComposeResult, RenderResult
from textual.widgets import (
    Header, Footer, Static, Input, Button, DataTable, 
    Label, TabbedContent, TabPane, Select, ListView, 
    ListItem, TextArea, LoadingIndicator, ProgressBar,
    Digits, Checkbox, DirectoryTree
)
from textual.containers import Horizontal, Vertical, ScrollableContainer, Container, Grid, VerticalScroll
from textual.screen import ModalScreen
from textual import work, on
from textual.binding import Binding
from textual.message import Message
from textual.reactive import reactive

# Project paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_JSON = os.path.join(BASE_DIR, "state.json")

from app.core.state_manager import StateManager
from app.core.audio_engine import AudioEngine
from app.core.library_manager_engine import LibraryManagerEngine
from app.services.strategy_manager import StrategyManager
from app.services.dispatcher import TaskDispatcher
from app.models.schemas import RenderConfig, UploadConfig, PrivacyEnum

# --- Custom Widgets ---

class Island(Container):
    """A minimalist panel with breathing room."""
    pass

class LogModal(ModalScreen):
    """A modal to view task logs."""
    def __init__(self, task_id, log_text, **kwargs):
        super().__init__(**kwargs)
        self.task_id = task_id
        self.log_text = log_text

    def compose(self) -> ComposeResult:
        with Container(id="log-container"):
            yield Label(f"LOGS FOR TASK #{self.task_id}", classes="section-label")
            yield TextArea(self.log_text, id="log-text", read_only=True)
            yield Button("CLOSE", id="btn-close-log", variant="primary")

    @on(Button.Pressed, "#btn-close-log")
    def exit_modal(self) -> None:
        self.app.pop_screen()

class ImportModal(ModalScreen):
    """A modal for scanning and importing assets."""
    def __init__(self, library_engine, callback, **kwargs):
        super().__init__(**kwargs)
        self.library_engine = library_engine
        self.callback = callback
        self.found_assets = []

    def compose(self) -> ComposeResult:
        with Container(id="import-modal-container"):
            yield Label("IMPORT BEAT ASSETS", classes="section-label")
            
            with Vertical(classes="island"):
                yield Label("Search Directory")
                with Horizontal(id="import-path-row"):
                    yield Input(placeholder="/path/to/beats...", id="import-search-path")
                    yield Button("...", id="btn-import-browse", classes="btn-icon")
                
                yield Checkbox("Delete original files after successful import", id="import-delete-source", value=False)
                yield Button("SCAN DIRECTORY", id="btn-import-scan", variant="primary")
            
            yield Label("FOUND ASSETS", classes="section-label")
            yield DataTable(id="import-results-table", cursor_type="row")
            
            with Horizontal(id="import-modal-buttons"):
                yield Button("CLOSE", id="btn-import-close")
                yield Button("IMPORT SELECTED", id="btn-import-collect", variant="primary")
                yield Button("IMPORT ALL", id="btn-import-all", variant="success")

    def on_mount(self) -> None:
        table = self.query_one("#import-results-table", DataTable)
        table.add_columns("NAME", "AUDIO FILE", "NOTES")

    @on(Button.Pressed, "#btn-import-browse")
    def handle_browse(self) -> None:
        def on_path_selected(path: str | None) -> None:
            if path:
                self.query_one("#import-search-path", Input).value = path
        self.app.push_screen(PathPicker(), on_path_selected)

    @on(Button.Pressed, "#btn-import-scan")
    def handle_scan(self) -> None:
        try:
            path = self.query_one("#import-search-path", Input).value
            if not path or not os.path.exists(path):
                self.app.notify("Please select a valid directory", severity="error")
                return
            
            # Ensure it's a directory
            if os.path.isfile(path):
                path = os.path.dirname(path)

            self.found_assets = self.library_engine.scan_for_import(path)
            table = self.query_one("#import-results-table", DataTable)
            table.clear()
            for asset in self.found_assets:
                table.add_row(
                    asset['name'],
                    os.path.basename(asset['audio_path']),
                    "YES" if asset['notes_path'] else "NO"
                )
            self.app.notify(f"Found {len(self.found_assets)} potential assets.")
        except Exception as e:
            self.app.notify(f"Scan failed: {str(e)}", severity="error")

    @on(Button.Pressed, "#btn-import-collect")
    def handle_collect(self) -> None:
        try:
            table = self.query_one("#import-results-table", DataTable)
            if table.cursor_row is not None:
                idx = table.cursor_row
                if 0 <= idx < len(self.found_assets):
                    asset_data = self.found_assets[idx]
                    delete_after = self.query_one("#import-delete-source", Checkbox).value
                    
                    asset = self.library_engine.import_beat_asset(
                        name=asset_data['name'],
                        audio_source=asset_data['audio_path'],
                        notes_source=asset_data['notes_path'],
                        delete_source=delete_after
                    )
                    self.app.notify(f"Successfully imported: {asset.name}", severity="information")
                    self.callback() # Trigger refresh in parent
                    self.handle_scan() 
                else:
                    self.app.notify("No valid asset selected.", severity="warning")
            else:
                self.app.notify("No asset selected in table", severity="warning")
        except Exception as e:
            import traceback
            with open("crash.log", "w") as f:
                f.write(traceback.format_exc())
            self.app.notify(f"Import failed: {str(e)}", severity="error")

    @on(Button.Pressed, "#btn-import-all")
    def handle_import_all(self) -> None:
        if not self.found_assets:
            self.app.notify("No assets to import.", severity="warning")
            return
            
        try:
            delete_after = self.query_one("#import-delete-source", Checkbox).value
            count = 0
            
            for asset_data in self.found_assets:
                self.library_engine.import_beat_asset(
                    name=asset_data['name'],
                    audio_source=asset_data['audio_path'],
                    notes_source=asset_data['notes_path'],
                    delete_source=delete_after
                )
                count += 1
                
            self.app.notify(f"Successfully imported {count} assets.", severity="information")
            self.callback() # Trigger refresh in parent
            self.handle_scan() 
            
        except Exception as e:
            import traceback
            with open("crash.log", "w") as f:
                f.write(traceback.format_exc())
            self.app.notify(f"Bulk import failed: {str(e)}", severity="error")

    @on(Button.Pressed, "#btn-import-close")
    def close_modal(self) -> None:
        self.dismiss()

class PathPicker(ModalScreen):
    """A modal to pick a directory."""
    def __init__(self, initial_path: str = os.path.expanduser("~"), **kwargs):
        super().__init__(**kwargs)
        self.initial_path = initial_path

    def compose(self) -> ComposeResult:
        with Container(id="picker-container"):
            yield Label("SELECT DIRECTORY / FILE", classes="section-label")
            yield DirectoryTree(self.initial_path, id="picker-tree")
            with Horizontal(id="picker-buttons"):
                yield Button("CANCEL", id="btn-picker-cancel")
                yield Button("SELECT", id="btn-picker-select", variant="success")

    @on("DirectoryTree.FileSelected")
    def handle_selected(self, event: DirectoryTree.FileSelected) -> None:
        self.dismiss(str(event.path))

    @on("DirectoryTree.DirectorySelected")
    def handle_dir_selected(self, event: DirectoryTree.DirectorySelected) -> None:
        pass

    @on(Button.Pressed, "#btn-picker-cancel")
    def cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#btn-picker-select")
    def select_current(self) -> None:
        tree = self.query_one("#picker-tree", DirectoryTree)
        if tree.cursor_node and tree.cursor_node.data:
            try:
                path = str(tree.cursor_node.data.path)
                self.dismiss(path)
            except AttributeError:
                self.dismiss(str(tree.cursor_node.data))
        else:
            self.dismiss(str(tree.path))

class DashboardTab(Container):
    """Main view with stats and current activity."""
    
    total_tasks = reactive(0)
    finished_tasks = reactive(0)
    error_tasks = reactive(0)
    active_task_name = reactive("IDLE")
    active_task_progress = reactive(0.0)

    def compose(self) -> ComposeResult:
        with Vertical(classes="tab-container"):
            with Horizontal(id="stats-row"):
                with Vertical(classes="stats-card"):
                    yield Label("TOTAL TASKS", classes="stats-label")
                    yield Digits("0", id="stat-total")
                with Vertical(classes="stats-card"):
                    yield Label("FINISHED", classes="stats-label")
                    yield Digits("0", id="stat-finished")
                with Vertical(classes="stats-card"):
                    yield Label("ERRORS", classes="stats-label")
                    yield Digits("0", id="stat-errors")
            
            with Vertical(id="active-task-container"):
                yield Label("CURRENTLY PROCESSING", classes="section-label")
                yield Label("IDLE", id="active-task-title")
                yield ProgressBar(total=100, show_eta=False, id="active-progress")

    def on_mount(self) -> None:
        self.set_interval(1.0, self.update_stats)

    def update_stats(self) -> None:
        state = StateManager(STATE_JSON)
        tasks = state.get_tasks()
        
        self.total_tasks = len(tasks)
        self.finished_tasks = len([t for t in tasks if t['status'] in ['Finished', 'Uploaded', 'Uploaded Metadata']])
        self.error_tasks = len([t for t in tasks if t['status'] == 'Error'])
        
        processing = [t for t in tasks if t['status'] == 'Processing']
        if processing:
            task = processing[0]
            self.active_task_name = f"{task['type']}: {os.path.basename(task['target'])}"
            self.active_task_progress = 50.0 
        else:
            self.active_task_name = "WORKER STANDBY"
            self.active_task_progress = 0.0

    def watch_total_tasks(self, value: int) -> None:
        self.query_one("#stat-total", Digits).update(str(value))

    def watch_finished_tasks(self, value: int) -> None:
        self.query_one("#stat-finished", Digits).update(str(value))

    def watch_error_tasks(self, value: int) -> None:
        self.query_one("#stat-errors", Digits).update(str(value))

    def watch_active_task_name(self, value: str) -> None:
        self.query_one("#active-task-title", Label).update(value)

    def watch_active_task_progress(self, value: float) -> None:
        self.query_one("#active-progress", ProgressBar).progress = value

class ProductionTab(Container):
    def compose(self) -> ComposeResult:
        with Vertical(classes="tab-container"):
            with Island(classes="form-island"):
                yield Label("RENDER CONFIGURATION", classes="section-label")
                yield Label("Audio Source")
                yield Input(placeholder="Path to .wav / .mp3", id="prod-audio", value=os.path.join(BASE_DIR, "dummy_assets/test_beat.mp3"))
                yield Label("Cover Art")
                yield Input(placeholder="Path to .png / .jpg", id="prod-image", value=os.path.join(BASE_DIR, "dummy_assets/test_cover.png"))
                yield Label("Output Path")
                yield Input(placeholder="Render destination...", id="prod-video", value=os.path.join(BASE_DIR, "output.mp4"))
                yield Button("QUEUE RENDER JOB", id="btn-render-start", variant="success")

class LibraryTab(Container):
    def compose(self) -> ComposeResult:
        with Horizontal(id="library-header"):
            yield Label("LIBRARY ASSETS", classes="section-label")
            yield Button("+ IMPORT BEATS", id="btn-open-import", variant="success")
        
        with Vertical(id="library-main-content"):
            yield DataTable(id="library-table", cursor_type="row")

    def on_mount(self) -> None:
        table = self.query_one("#library-table", DataTable)
        table.add_columns("ID", "NAME", "TYPE", "BPM", "KEY", "DURATION")
        
        self.library_engine = LibraryManagerEngine()
        self.refresh_library()

    @on(Button.Pressed, "#btn-open-import")
    def handle_open_import(self) -> None:
        self.app.push_screen(ImportModal(self.library_engine, self.refresh_library))

    def refresh_library(self) -> None:
        table = self.query_one("#library-table", DataTable)
        table.clear()
        assets = self.library_engine.get_assets()
        for asset in assets:
            duration = f"{asset.get('duration', 0):.1f}s" if asset.get('duration') else "N/A"
            table.add_row(
                asset.get('id', 'N/A'),
                asset.get('name', 'Unknown'),
                asset.get('type', 'N/A').upper(),
                str(asset.get('bpm', 'N/A')),
                str(asset.get('key', 'N/A')),
                duration
            )

class YoutubeTab(Container):
    def compose(self) -> ComposeResult:
        with Vertical(classes="tab-container"):
            with Island(classes="form-island"):
                yield Label("YOUTUBE PUBLISHING", classes="section-label")
                yield Label("Video File")
                yield Input(placeholder="Path to .mp4", id="yt-video", value=os.path.join(BASE_DIR, "output.mp4"))
                yield Label("Title")
                yield Input(placeholder="Catchy title...", id="yt-title")
                yield Label("Description")
                yield TextArea(id="yt-desc", classes="small-text-area")
                
                with Horizontal(classes="multi-input-row"):
                    yield Select([("Music", "10"), ("Entertainment", "24")], id="yt-cat", value="10")
                    yield Select([("Private", "private"), ("Public", "public")], id="yt-privacy", value="private")
                
                yield Label("Schedule (ISO 8601, optional)")
                yield Input(placeholder="YYYY-MM-DDTHH:MM:SSZ", id="yt-schedule")
                
                yield Button("QUEUE UPLOAD", id="btn-yt-upload", variant="primary")

class StrategiesTab(Container):
    def compose(self) -> ComposeResult:
        with Horizontal(id="strat-row"):
            with VerticalScroll(id="strat-left", classes="island"):
                yield Label("1. STRATEGY (JSON for LLM)", classes="section-label")
                yield TextArea(id="strat-json", classes="json-editor")
                yield Button("SAVE STRATEGY", id="btn-strat-save", variant="primary")
                
                yield Label("2. MASTER ROUTINE (PLAN)", classes="section-label")
                yield TextArea(id="plan-json", classes="json-editor")
                yield Button("SAVE & COMPILE QUEUE", id="btn-plan-compile", variant="success")
            
            with VerticalScroll(id="strat-right", classes="island"):
                yield Label("3. GENERATED QUEUE", classes="section-label")
                yield DataTable(id="strat-queue-table", cursor_type="row")
                
                yield Label("TASK PARAMETERS (Selected Task)", classes="section-label")
                yield TextArea(id="task-params-json", classes="json-editor-small")
                yield Button("SAVE SELECTED PARAMS", id="btn-save-params", variant="primary")
                
                yield Label("ISSUES / ALERTS", classes="section-label")
                yield ListView(id="strat-issues-list", classes="issues-list")
                
                yield Button("ACTIVATE SELECTED", id="btn-strat-activate", variant="warning")
                with Horizontal(classes="status-bar-simple"):
                    yield Label("ASSETS:", id="asset-label")
                    yield Label("READY", id="asset-status")

    def on_mount(self) -> None:
        table = self.query_one("#strat-queue-table", DataTable)
        table.add_columns("DATE/TIME", "ACTION", "NICHE", "STATUS")
        self.load_data()
        self.refresh_queue()
        self.check_assets()

    def load_data(self) -> None:
        sm = StrategyManager()
        self.query_one("#strat-json", TextArea).load_text(json.dumps(sm.get_strategy(), indent=4))
        self.query_one("#plan-json", TextArea).load_text(json.dumps(sm.get_plan(), indent=4))

    def check_assets(self) -> None:
        sm = StrategyManager()
        assets = sm.check_assets()
        self.query_one("#asset-status", Label).update(f"{assets['status'].upper()} (Audio: {assets['audio']}, Images: {assets['images']})")

    def refresh_queue(self) -> None:
        sm = StrategyManager()
        queue = sm.get_queue()
        table = self.query_one("#strat-queue-table", DataTable)
        table.clear()
        for item in queue:
            table.add_row(
                item['timestamp'],
                item['action'],
                item['details'].get('niche', 'Generic'),
                item['status'].upper()
            )
        self.refresh_issues()

    def refresh_issues(self) -> None:
        sm = StrategyManager()
        issues = sm.validate_queue()
        list_view = self.query_one("#strat-issues-list", ListView)
        list_view.clear()
        if not issues:
            list_view.append(ListItem(Label("✅ All parameters valid", classes="issue-ok")))
        else:
            for issue_entry in issues:
                row = issue_entry['row']
                for err in issue_entry['errors']:
                    msg = f"Row {row}: Missing {err['field']}" if err['reason'] == 'missing_parameter' else f"Row {row}: {err['reason']} ({err.get('path', '')})"
                    list_view.append(ListItem(Label(f"⚠️ {msg}", classes="issue-warn")))

    @on(Button.Pressed, "#btn-strat-save")
    def handle_strat_save(self) -> None:
        try:
            raw = self.query_one("#strat-json", TextArea).text
            data = json.loads(raw)
            StrategyManager().save_strategy(data)
            self.app.notify("Strategy JSON saved!", title="Success")
        except Exception as e:
            self.app.notify(f"Invalid JSON: {str(e)}", variant="error")

    @on(Button.Pressed, "#btn-plan-compile")
    def handle_plan_compile(self) -> None:
        try:
            raw = self.query_one("#plan-json", TextArea).text
            data = json.loads(raw)
            sm = StrategyManager()
            sm.save_plan(data)
            sm.compile_queue_from_plan()
            self.refresh_queue()
            self.check_assets()
            self.app.notify("Plan saved and Queue compiled!", title="Success")
        except Exception as e:
            self.app.notify(f"Invalid Plan JSON: {str(e)}", variant="error")

    @on(Button.Pressed, "#btn-strat-activate")
    def handle_strat_activate(self) -> None:
        table = self.query_one("#strat-queue-table", DataTable)
        if table.cursor_row is not None:
            idx = table.cursor_row
            
            # Pre-activation validation check
            sm = StrategyManager()
            issues = sm.validate_queue()
            # Only block if the issue belongs to the selected row
            row_issues = [iss for issue in issues if (iss := issue) and f"Row {idx}:" in issue]
            
            if row_issues:
                self.app.notify(f"Cannot activate: {row_issues[0]}", variant="error")
                return

            task_id = self.app.dispatcher.activate_from_queue(idx)
            if task_id:
                self.refresh_queue()
                self.app.notify(f"Task #{task_id} activated!", title="Success")
            else:
                self.app.notify("Failed to activate task (maybe already scheduled).", variant="error")

    @on(DataTable.RowSelected, "#strat-queue-table")
    def on_task_selected(self, event: DataTable.RowSelected) -> None:
        idx = event.cursor_row
        sm = StrategyManager()
        queue = sm.get_queue()
        if 0 <= idx < len(queue):
            details = queue[idx].get('details', {})
            self.query_one("#task-params-json", TextArea).load_text(json.dumps(details, indent=4))

    @on(Button.Pressed, "#btn-save-params")
    def handle_save_params(self) -> None:
        table = self.query_one("#strat-queue-table", DataTable)
        if table.cursor_row is not None:
            idx = table.cursor_row
            try:
                raw = self.query_one("#task-params-json", TextArea).text
                new_details = json.loads(raw)
                sm = StrategyManager()
                if sm.update_queue_item(idx, new_details):
                    self.refresh_queue()
                    self.app.notify("Task parameters updated!", title="Success")
            except Exception as e:
                self.app.notify(f"Invalid JSON: {str(e)}", variant="error")

class QueuePanel(Container):
    def compose(self) -> ComposeResult:
        yield Label("SYSTEM QUEUE (Double-click row for logs)", classes="section-label")
        yield DataTable(id="queue-table")

    def on_mount(self) -> None:
        table = self.query_one("#queue-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("ID", "TYPE", "TARGET", "STATUS")
        self.set_interval(2.0, self.update_queue)

    def update_queue(self) -> None:
        try:
            table = self.query_one("#queue-table", DataTable)
            state = StateManager(STATE_JSON)
            tasks = state.get_tasks()
            
            table.clear()
            for task in reversed(tasks):
                status = task['status']
                table.add_row(
                    f"#{task.doc_id}", 
                    task['type'], 
                    os.path.basename(task['target']), 
                    status.upper()
                )
        except: pass

    @on(DataTable.RowSelected, "#queue-table")
    def on_row_selected(self, event: DataTable.RowSelected) -> None:
        row_data = self.query_one("#queue-table", DataTable).get_row(event.row_key)
        task_id = int(row_data[0].replace("#", ""))
        state = StateManager(STATE_JSON)
        task = state.tasks_table.get(doc_id=task_id)
        if task:
            log = task.get("log", "No logs recorded yet.")
            self.app.push_screen(LogModal(task_id, log))

# --- Main App ---

class BeatManagerApp(App):
    TITLE = "BEAT MANAGER PRO"
    CSS_PATH = "styles.tcss"

    show_queue = reactive(True)

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("r", "refresh_all", "Refresh UI", show=True),
        Binding("ctrl+q", "toggle_queue", "Toggle Queue", show=True),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            with TabPane("DASHBOARD"):
                yield DashboardTab()
            with TabPane("PRODUCTION"):
                yield ProductionTab()
            with TabPane("LIBRARY"):
                yield LibraryTab()
            with TabPane("YOUTUBE"):
                yield YoutubeTab()
            with TabPane("STRATEGIES"):
                yield StrategiesTab()
        yield QueuePanel(id="queue-panel")
        with Horizontal(id="footer-bar"):
            yield Button("QUEUE [Ctrl+Q]", id="btn-toggle-queue")
            yield Footer()

    def action_toggle_queue(self) -> None:
        self.show_queue = not self.show_queue

    def watch_show_queue(self, show: bool) -> None:
        self.query_one("#queue-panel").set_class(not show, "hidden")

    @on(Button.Pressed, "#btn-toggle-queue")
    def handle_toggle_queue(self) -> None:
        self.action_toggle_queue()

    def on_mount(self) -> None:
        self.dispatcher = TaskDispatcher(BASE_DIR)
        self.notify("BeatManager Pro Online", title="System")

    def action_refresh_all(self) -> None:
        self.notify("Refreshing all data...", title="System")

    @work(exclusive=True, thread=True)
    @on(Button.Pressed, "#btn-render-start")
    def handle_render(self) -> None:
        audio = self.query_one("#prod-audio", Input).value
        image = self.query_one("#prod-image", Input).value
        output = self.query_one("#prod-video", Input).value
        
        config = RenderConfig(
            audio_path=audio,
            image_path=image,
            output_path=output,
            project_tag="tui_manual_render"
        )
        self.notify(f"RENDER STARTED: {os.path.basename(output)}")
        result = self.dispatcher.run_render(config)
        if result.success:
            self.notify(f"RENDER FINISHED: {os.path.basename(output)}", variant="success")
        else:
            self.notify(f"RENDER FAILED: {result.error_message}", variant="error")

    @work(exclusive=True, thread=True)
    @on(Button.Pressed, "#btn-yt-upload")
    def handle_yt_upload(self) -> None:
        video = self.query_one("#yt-video", Input).value
        title = self.query_one("#yt-title", Input).value
        description = self.query_one("#yt-desc", TextArea).text
        privacy = self.query_one("#yt-privacy", Select).value
        publish_at = self.query_one("#yt-schedule", Input).value or None
        
        config = UploadConfig(
            video_path=video,
            title=title,
            description=description,
            privacy=PrivacyEnum(privacy),
            publish_at=publish_at
        )
        self.notify(f"UPLOAD STARTED: {title}")
        result = self.dispatcher.run_upload(config)
        if result.success:
            self.notify(f"UPLOAD FINISHED: {title} (ID: {result.output_path})", variant="success")
        else:
            self.notify(f"UPLOAD FAILED: {result.error_message}", variant="error")

if __name__ == "__main__":
    app = BeatManagerApp()
    app.run()
