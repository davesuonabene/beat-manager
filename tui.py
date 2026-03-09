import os
import glob
import json
import time
from datetime import datetime
from typing import List, Tuple, Dict, Any

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

class LibraryFilterBar(Horizontal):
    """Modular bar for filtering library assets."""
    class Changed(Message):
        def __init__(self, search: str, type_filter: str):
            self.search = search
            self.type_filter = type_filter
            super().__init__()

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Search assets...", id="lib-filter-search")
        yield Select([
            ("ALL TYPES", "all"),
            ("RAW AUDIO", "raw"),
            ("BEATS", "beat"),
            ("IMAGES", "cover")
        ], id="lib-filter-type", value="all")

    @on(Input.Changed, "#lib-filter-search")
    @on(Select.Changed, "#lib-filter-type")
    def handle_change(self) -> None:
        search = self.query_one("#lib-filter-search", Input).value
        type_filter = self.query_one("#lib-filter-type", Select).value
        self.post_message(self.Changed(search, str(type_filter)))

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

class ImportOverlay(Container):
    """A slide-up overlay for scanning and importing assets."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.found_assets = []

    def compose(self) -> ComposeResult:
        yield Label("IMPORT ASSETS", classes="section-label")
        
        with Horizontal(id="import-controls-row"):
            with Vertical(id="import-path-col"):
                with Horizontal(id="import-path-row"):
                    yield Input(placeholder="/path/to/assets...", id="import-search-path")
                    yield Button("...", id="btn-import-browse", classes="btn-icon", tooltip="Browse")
                    yield Button("🔄", id="btn-import-scan", classes="btn-icon", tooltip="Refresh Directory")
            with Vertical(id="import-toggles-col"):
                yield Checkbox("Delete sources after import", id="import-delete-source", value=False)
                yield Checkbox("Skip existing items", id="import-skip-dupes", value=True)
        
        yield DataTable(id="import-results-table", cursor_type="row")
        
        with Horizontal(id="import-modal-buttons"):
            yield Button("CLOSE", id="btn-import-close")
            yield Button("▶ PREVIEW", id="btn-import-preview", variant="warning")
            yield Button("IMPORT SELECTED", id="btn-import-collect", variant="primary")
            yield Button("IMPORT ALL", id="btn-import-all", variant="success")

    def on_mount(self) -> None:
        table = self.query_one("#import-results-table", DataTable)
        table.add_columns("NAME", "TYPE", "PATH", "STATUS")

    @on(Button.Pressed, "#btn-import-preview")
    def handle_preview(self) -> None:
        table = self.query_one("#import-results-table", DataTable)
        if table.cursor_row is not None:
            idx = table.cursor_row
            if 0 <= idx < len(self.found_assets):
                asset_data = self.found_assets[idx]
                if asset_data['type'] == 'audio':
                    self.app.audio_engine.play_preview(asset_data['path'])
                    self.app.notify(f"Previewing: {os.path.basename(asset_data['path'])}")
                else:
                    self.app.notify("Only audio can be previewed", severity="warning")

    @on(Button.Pressed, "#btn-import-close")
    def close_overlay(self) -> None:
        self.app.audio_engine.stop_preview()
        self.add_class("hidden")
        self.app.action_refresh_library() # Custom action to trigger refresh from app level

    @on(Button.Pressed, "#btn-import-browse")
    def handle_browse(self) -> None:
        def on_path_selected(path: str | None) -> None:
            if path:
                self.query_one("#import-search-path", Input).value = path
                self.handle_scan() 
        self.app.push_screen(PathPicker(), on_path_selected)

    @on(Button.Pressed, "#btn-import-scan")
    @on(Input.Submitted, "#import-search-path")
    def handle_scan(self) -> None:
        try:
            path = self.query_one("#import-search-path", Input).value
            if not path or not os.path.exists(path):
                self.app.notify("Please select a valid directory", severity="error")
                return
            
            if os.path.isfile(path):
                path = os.path.dirname(path)

            self.found_assets = self.app.library_engine.scan_for_import(path)
            table = self.query_one("#import-results-table", DataTable)
            table.clear()
            for asset in self.found_assets:
                table.add_row(
                    asset['name'],
                    asset['type'].upper(),
                    os.path.basename(asset['path']),
                    asset.get('status', 'Ready')
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
                    skip_dupes = self.query_one("#import-skip-dupes", Checkbox).value
                    
                    if skip_dupes and asset_data.get('status') == 'Exists':
                        self.app.notify(f"Skipped {asset_data['name']} (Already exists)", severity="warning")
                        return

                    if asset_data['type'] == 'audio':
                        asset = self.app.library_engine.import_raw_audio(
                            name=asset_data['name'],
                            audio_source=asset_data['path'],
                            notes_source=asset_data['notes_path'],
                            delete_source=delete_after
                        )
                    else: 
                        asset = self.app.library_engine.import_image(
                            name=asset_data['name'],
                            source_path=asset_data['path'],
                            delete_source=delete_after
                        )
                        
                    self.app.notify(f"Successfully imported: {asset.name}", severity="information")
                    self.handle_scan() 
                else:
                    self.app.notify("No valid asset selected.", severity="warning")
            else:
                self.app.notify("No asset selected in table", severity="warning")
        except Exception as e:
            self.app.notify(f"Import failed: {str(e)}", severity="error")

    @on(Button.Pressed, "#btn-import-all")
    def handle_import_all(self) -> None:
        if not self.found_assets:
            self.app.notify("No assets to import.", severity="warning")
            return
            
        try:
            delete_after = self.query_one("#import-delete-source", Checkbox).value
            skip_dupes = self.query_one("#import-skip-dupes", Checkbox).value
            count = 0
            skipped = 0
            
            for asset_data in self.found_assets:
                if skip_dupes and asset_data.get('status') == 'Exists':
                    skipped += 1
                    continue
                    
                if asset_data['type'] == 'audio':
                    self.app.library_engine.import_raw_audio(
                        name=asset_data['name'],
                        audio_source=asset_data['path'],
                        notes_source=asset_data['notes_path'],
                        delete_source=delete_after
                    )
                else: 
                    self.app.library_engine.import_image(
                        name=asset_data['name'],
                        source_path=asset_data['path'],
                        delete_source=delete_after
                    )
                count += 1
                
            msg = f"Imported {count} assets."
            if skipped > 0: msg += f" Skipped {skipped} duplicates."
            self.app.notify(msg, severity="information")
            self.handle_scan() 
        except Exception as e:
            self.app.notify(f"Bulk import failed: {str(e)}", severity="error")

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
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.editing_coordinate = None
        self.editing_field = None
        self.editing_asset_id = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="library-header"):
            yield Label("LIBRARY", id="lib-title")
            yield LibraryFilterBar()
            with Horizontal(id="lib-actions"):
                yield Button("▶", id="btn-library-preview", variant="warning", tooltip="Preview [P]")
                yield Button("🎹", id="btn-library-make-beat", variant="primary", tooltip="Beat-ify [B]")
                yield Button("🖼️", id="btn-library-link-cover", variant="default", tooltip="Set Cover [C]")
                yield Button("🔄", id="btn-library-sync", variant="default", tooltip="Sync [F5]")
                yield Button("➕", id="btn-open-import", variant="success", tooltip="Import")
                yield Button("🗑️", id="btn-library-delete", variant="error", tooltip="Delete [DEL]")
        
        with Vertical(id="library-main-content"):
            with Container(id="library-table-container"):
                yield DataTable(id="library-table", cursor_type="cell")
                yield Input(id="inline-editor", classes="hidden")

    BINDINGS = [
        Binding("p", "preview", "Preview"),
        Binding("s", "stop", "Stop"),
        Binding("b", "make_beat", "Make Beat"),
        Binding("r", "rename_asset", "Rename"),
        Binding("delete", "delete_asset", "Delete"),
        Binding("ctrl+a", "select_all", "Select All"),
        Binding("f5", "sync_library", "Sync with disk"),
        Binding("c", "set_cover", "Set as Cover"),
        Binding("escape", "cancel_edit", "Cancel Edit", show=False),
    ]

    def _get_selected_ids(self) -> List[str]:
        try:
            table = self.query_one("#library-table", DataTable)
        except: return []
        
        selected_ids = []
        selected_rows = getattr(table, "selected_rows", set())
        if selected_rows:
            for key in selected_rows:
                try:
                    row = table.get_row(key)
                    selected_ids.append(str(row[0]))
                except: continue
        elif table.cursor_row is not None:
            try:
                row_keys = list(table.rows.keys())
                if 0 <= table.cursor_row < len(row_keys):
                    row = table.get_row(row_keys[table.cursor_row])
                    selected_ids.append(str(row[0]))
            except: pass
        return selected_ids

    def action_preview(self) -> None:
        ids = self._get_selected_ids()
        if not ids: return
        
        asset_id = ids[0]
        all_assets = self.library_engine.get_assets()
        asset = next((a for a in all_assets if str(a.get('id')) == asset_id), None)
        
        if asset:
            if asset.get('data_type') != 'audio':
                self.app.notify("Only audio assets can be previewed.", severity="warning")
                return

            asset_type = asset.get('asset_type', asset.get('type', 'raw'))
            audio_path = ""
            if asset_type == 'raw':
                audio_path = asset.get('path', '')
            else:
                main_file = asset.get('versions', {}).get('main', asset.get('audio_file', ''))
                audio_path = os.path.join(asset.get('path', ''), main_file)
            
            if audio_path and os.path.exists(audio_path) and os.path.isfile(audio_path):
                self.app.audio_engine.play_preview(audio_path)
                self.app.notify(f"Previewing: {asset.get('name', 'Unknown')}")
            else:
                self.app.notify(f"Audio file not found", severity="error")

    def action_make_beat(self) -> None:
        ids = self._get_selected_ids()
        if not ids:
            self.app.notify("No assets selected", severity="warning")
            return
            
        count = 0
        for asset_id in ids:
            try:
                self.library_engine.create_beat_from_audio(asset_id)
                count += 1
            except Exception: continue
        
        if count > 0:
            self.app.notify(f"Created {count} beats.")
            self.refresh_library()

    def action_set_cover(self) -> None:
        ids = self._get_selected_ids()
        all_assets = self.library_engine.get_assets()
        selected = [a for a in all_assets if str(a.get('id')) in ids]
        
        beats = [a for a in selected if a.get('asset_type') == 'beat']
        images = [a for a in selected if a.get('data_type') == 'image']
        
        if not beats or not images:
            self.app.notify("Select at least one BEAT and one IMAGE to link.", severity="warning")
            return
            
        try:
            self.library_engine.set_beat_cover(beats[0]['id'], images[0]['id'])
            self.app.notify(f"Cover linked: {images[0]['name']} -> {beats[0]['name']}", severity="information")
            self.refresh_library()
        except Exception as e:
            self.app.notify(f"Link failed: {str(e)}", severity="error")

    def action_delete_asset(self) -> None:
        try:
            ids = self._get_selected_ids()
            if not ids:
                self.app.notify("No assets selected", severity="warning")
                return
                
            table = self.query_one("#library-table", DataTable)
            if hasattr(table, "selected_rows"):
                table.selected_rows = set()
            
            deleted_count = 0
            for asset_id in ids:
                if self.library_engine.delete_asset(asset_id):
                    deleted_count += 1
                    
            if deleted_count > 0:
                self.app.notify(f"Deleted {deleted_count} assets.")
                self.refresh_library()
        except Exception as e:
            self.app.notify(f"Delete failed: {str(e)}", severity="error")

    def action_sync_library(self) -> None:
        self.app.notify("Syncing library...")
        removed = self.library_engine.sync_library_with_disk()
        if removed > 0:
            self.app.notify(f"Pruned {removed} missing assets.", severity="warning")
        else:
            self.app.notify("Library is in sync with disk.")
        self.refresh_library()

    def action_select_all(self) -> None:
        table = self.query_one("#library-table", DataTable)
        for row_key in table.rows:
            table.select_row(row_key)
        self.app.notify("Selected all filtered assets")

    def action_stop(self) -> None:
        self.app.audio_engine.stop_preview()
        self.app.notify("Preview stopped.")

    @on(Button.Pressed, "#btn-library-sync")
    def handle_sync(self) -> None:
        self.action_sync_library()

    @on(Button.Pressed, "#btn-library-preview")
    def handle_preview(self) -> None:
        self.action_preview()

    @on(Button.Pressed, "#btn-library-make-beat")
    def handle_make_beat(self) -> None:
        self.action_make_beat()

    @on(Button.Pressed, "#btn-library-link-cover")
    def handle_link_cover(self) -> None:
        self.action_set_cover()

    @on(Button.Pressed, "#btn-library-delete")
    def handle_delete(self) -> None:
        self.action_delete_asset()

    def action_toggle_import(self) -> None:
        self.app.action_toggle_import()

    @on(Button.Pressed, "#btn-open-import")
    def handle_open_import(self) -> None:
        self.action_toggle_import()

    def on_library_filter_bar_changed(self, event: LibraryFilterBar.Changed) -> None:
        self.refresh_library(search=event.search, type_filter=event.type_filter)

    def on_mount(self) -> None:
        table = self.query_one("#library-table", DataTable)
        try: table.multiselect = True
        except: pass
        table.add_columns("ID", "NAME", "TYPE", "DATA", "BPM", "KEY", "DUR")
        self.library_engine = LibraryManagerEngine()
        self.assets = []
        self.refresh_library()

    @on(DataTable.CellSelected, "#library-table")
    def handle_cell_selected(self, event: DataTable.CellSelected) -> None:
        try:
            col_idx = event.coordinate.column
            if col_idx not in (1, 4, 5): # 1: NAME, 4: BPM, 5: KEY
                return
                
            table = self.query_one("#library-table", DataTable)
            row_keys = list(table.rows.keys())
            if event.coordinate.row >= len(row_keys):
                return
                
            row_key = row_keys[event.coordinate.row]
            row_data = table.get_row(row_key)
            asset_id = str(row_data[0])
            
            asset = next((a for a in self.assets if str(a.get('id')) == asset_id), None)
            if not asset: return

            field_map = {1: "name", 4: "bpm", 5: "key"}
            field_name = field_map[col_idx]
            
            # BPM and Key only editable for Beats
            asset_type = asset.get('asset_type', asset.get('type', 'raw'))
            if field_name in ("bpm", "key") and asset_type != "beat":
                self.app.notify("BPM and Key can only be edited for BEATS.", severity="warning")
                return

            current_val = asset.get(field_name, "")
            if current_val is None: current_val = ""

            # Position inline editor
            inp = self.query_one("#inline-editor", Input)
            region = table._get_cell_region(event.coordinate)
            
            y_offset = region.y - table.scroll_offset.y
            x_offset = region.x - table.scroll_offset.x
            
            # If scrolled out of view, don't show
            if y_offset < 0 or y_offset >= table.size.height:
                return
                
            inp.styles.offset = (x_offset, y_offset)
            inp.styles.width = region.width
            
            inp.value = str(current_val)
            self.editing_field = field_name
            self.editing_asset_id = asset_id
            
            inp.remove_class("hidden")
            inp.focus()

        except Exception as e:
            pass

    @on(Input.Submitted, "#inline-editor")
    def handle_inline_edit_submit(self, event: Input.Submitted) -> None:
        new_val = event.value
        inp = self.query_one("#inline-editor", Input)
        inp.add_class("hidden")
        self.query_one("#library-table", DataTable).focus()

        if not getattr(self, "editing_asset_id", None): return

        field_name = self.editing_field
        asset_id = self.editing_asset_id
        
        # Reset tracking
        self.editing_asset_id = None
        self.editing_field = None

        try:
            if field_name == "name":
                self.library_engine.rename_asset(asset_id, new_val)
            else:
                # Parse BPM to float if possible
                val_to_save = new_val
                if field_name == "bpm":
                    try: val_to_save = float(new_val) if new_val.strip() else None
                    except: return self.app.notify("Invalid BPM format.", severity="error")
                
                self.library_engine.update_asset(asset_id, {field_name: val_to_save})
                
            self.refresh_library()
        except Exception as e:
            self.app.notify(f"Failed to update: {str(e)}", severity="error")

    def action_cancel_edit(self) -> None:
        try:
            inp = self.query_one("#inline-editor", Input)
            if not inp.has_class("hidden"):
                inp.add_class("hidden")
                self.query_one("#library-table", DataTable).focus()
                self.editing_asset_id = None
                self.editing_field = None
        except: pass

    def refresh_library(self, search: str | None = None, type_filter: str | None = None) -> None:
        try:
            table = self.query_one("#library-table", DataTable)
            if search is None or type_filter is None:
                try:
                    fb = self.query_one(LibraryFilterBar)
                    search = fb.query_one("#lib-filter-search", Input).value if search is None else search
                    type_filter = str(fb.query_one("#lib-filter-type", Select).value) if type_filter is None else type_filter
                except:
                    search = search or ""
                    type_filter = type_filter or "all"

            all_assets = self.library_engine.get_assets()
            filtered = []
            for a in all_assets:
                a_type = a.get('asset_type', a.get('type', 'raw'))
                if type_filter != "all" and a_type != type_filter: continue
                if search and search.lower() not in a.get('name', '').lower(): continue
                filtered.append(a)
            
            self.assets = filtered
            table.clear()
            for a in self.assets:
                dur = f"{a.get('duration', 0):.1f}s" if a.get('duration') else "N/A"
                d_type = a.get('data_type', 'AUDIO').upper()
                bpm = str(a.get('bpm', '')) if a.get('bpm') else ""
                key = str(a.get('key', '')) if a.get('key') else ""
                
                table.add_row(
                    a.get('id', 'N/A'),
                    a.get('name', 'Unknown'),
                    a.get('asset_type', 'N/A').upper(),
                    d_type,
                    bpm,
                    key,
                    dur
                )
        except Exception as e:
            import traceback
            with open("crash.log", "a") as f:
                f.write(f"\n[{datetime.now().isoformat()}] refresh_library CRASH: {str(e)}\n{traceback.format_exc()}\n")

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
            self.app.notify("Strategy JSON saved!", severity="information")
        except Exception as e:
            self.app.notify(f"Invalid JSON: {str(e)}", severity="error")

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
            self.app.notify("Plan saved and Queue compiled!", severity="information")
        except Exception as e:
            self.app.notify(f"Invalid Plan JSON: {str(e)}", severity="error")

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
                self.app.notify(f"Cannot activate: {row_issues[0]}", severity="error")
                return

            task_id = self.app.dispatcher.activate_from_queue(idx)
            if task_id:
                self.refresh_queue()
                self.app.notify(f"Task #{task_id} activated!", severity="information")
            else:
                self.app.notify("Failed to activate task (maybe already scheduled).", severity="error")

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
                    self.app.notify("Task parameters updated!", severity="information")
            except Exception as e:
                self.app.notify(f"Invalid JSON: {str(e)}", severity="error")

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

    show_queue = reactive(False)
    show_import = reactive(False)

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("r", "refresh_all", "Refresh UI", show=True),
        Binding("ctrl+q", "toggle_queue", "Toggle Queue", show=True),
        Binding("ctrl+i", "toggle_import", "Toggle Import", show=True),
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
        yield QueuePanel(id="queue-panel", classes="hidden")
        yield ImportOverlay(id="import-overlay", classes="hidden")
        with Horizontal(id="footer-bar"):
            yield Button("QUEUE [Ctrl+Q]", id="btn-toggle-queue")
            yield Button("IMPORT [Ctrl+I]", id="btn-toggle-import")
            yield Footer()

    def action_toggle_queue(self) -> None:
        self.show_queue = not self.show_queue

    def watch_show_queue(self, show: bool) -> None:
        self.query_one("#queue-panel").set_class(not show, "hidden")

    @on(Button.Pressed, "#btn-toggle-queue")
    def handle_toggle_queue(self) -> None:
        self.action_toggle_queue()

    def action_toggle_import(self) -> None:
        self.show_import = not self.show_import

    def watch_show_import(self, show: bool) -> None:
        self.query_one("#import-overlay").set_class(not show, "hidden")

    @on(Button.Pressed, "#btn-toggle-import")
    def handle_toggle_import(self) -> None:
        self.action_toggle_import()

    def on_mount(self) -> None:
        self.library_engine = LibraryManagerEngine()
        self.audio_engine = AudioEngine()
        self.dispatcher = TaskDispatcher(BASE_DIR)
        self.notify("BeatManager Pro Online", title="System")

    def on_error(self, error: Exception) -> None:
        import traceback
        with open("crash.log", "a") as f:
            f.write(f"\n[{datetime.now().isoformat()}] GLOBAL CRASH: {str(error)}\n{traceback.format_exc()}\n")
        super().on_error(error)

    def on_unmount(self) -> None:
        if hasattr(self, "audio_engine"):
            self.audio_engine.stop_preview()

    def action_refresh_library(self) -> None:
        try:
            self.query_one(LibraryTab).refresh_library()
        except: pass

    def action_refresh_all(self) -> None:
        self.notify("Refreshing all data...", title="System")
        self.action_refresh_library()

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
            self.notify(f"RENDER FINISHED: {os.path.basename(output)}", severity="information")
        else:
            self.notify(f"RENDER FAILED: {result.error_message}", severity="error")

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
            self.notify(f"UPLOAD FINISHED: {title} (ID: {result.output_path})", severity="information")
        else:
            self.notify(f"UPLOAD FAILED: {result.error_message}", severity="error")

if __name__ == "__main__":
    app = BeatManagerApp()
    app.run()
