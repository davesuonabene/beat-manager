import os
import glob
import json
import time
import math
import random
from datetime import datetime
from typing import List, Tuple, Dict, Any
from tinydb import Query
from textual.coordinate import Coordinate

from textual.app import App, ComposeResult, RenderResult
from textual.widgets import (
    Header, Footer, Static, Input, Button, DataTable, 
    Label, TabbedContent, TabPane, Select, ListView,
    ListItem, TextArea, LoadingIndicator, ProgressBar,
    Digits, Checkbox, DirectoryTree, Sparkline, Tabs, Tab
)
from textual.containers import Horizontal, Vertical, ScrollableContainer, Container, Grid, VerticalScroll
from textual.screen import ModalScreen
from textual import work, on, events
from textual.binding import Binding
from textual.message import Message
from textual.reactive import reactive

# Project paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_JSON = os.path.join(BASE_DIR, "state.json")

from app.core.state_manager import StateManager
from app.core.audio_engine import AudioEngine
from app.core.library_manager_engine import LibraryManagerEngine
from app.services.dispatcher import TaskDispatcher

# --- Custom Widgets ---

class ConfirmModal(ModalScreen):
    """A simple confirmation modal."""
    def __init__(self, message: str, **kwargs):
        super().__init__(**kwargs)
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-container"):
            yield Label("CONFIRMATION", classes="panel_title")
            yield Label(self.message, id="confirm-message")
            with Horizontal(id="confirm-buttons"):
                yield Button("CANCEL", id="btn-confirm-cancel", variant="error")
                yield Button("CONFIRM", id="btn-confirm-ok", variant="success")

    @on(Button.Pressed, "#btn-confirm-cancel")
    def cancel(self) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#btn-confirm-ok")
    def confirm(self) -> None:
        self.dismiss(True)

class TrashPicker(ModalScreen):
    """A modal for picking a trash folder to restore."""
    def __init__(self, trash_items: List[str], **kwargs):
        super().__init__(**kwargs)
        self.trash_items = trash_items

    def compose(self) -> ComposeResult:
        with Vertical(id="picker-container"):
            yield Label("SELECT TRASH BACKUP", classes="panel_title")
            with ScrollableContainer(id="trash-list-container"):
                yield ListView(*[ListItem(Label(item), id=f"trash_{i}") for i, item in enumerate(self.trash_items)], id="trash-list")
            with Horizontal(id="picker-buttons"):
                yield Button("CANCEL", id="btn-picker-cancel", variant="error")

    @on(ListView.Selected, "#trash-list")
    def handle_selected(self, event: ListView.Selected) -> None:
        idx = int(event.item.id.split("_")[1])
        self.dismiss(self.trash_items[idx])

    @on(Button.Pressed, "#btn-picker-cancel")
    def cancel(self) -> None:
        self.dismiss(None)

class ActionMenuOverlay(Vertical):
    """An overlay for asset actions in the power column."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.actions = []

    def compose(self) -> ComposeResult:
        yield Label("ACTION MENU", classes="panel_title")
        with Vertical(id="action-menu-content"):
            pass
        with Horizontal(id="modal-buttons"):
            yield Button("BACK", id="btn-action-close", variant="error")

    def set_actions(self, actions: List[Tuple[str, str]]) -> None:
        self.actions = actions
        content = self.query_one("#action-menu-content", Vertical)
        content.remove_children()
        for label, action in self.actions:
            content.mount(Button(label, id=f"ctx-{action}", variant="primary", classes="ctx-btn"))

    @on(Button.Pressed)
    def handle_action(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-action-close":
            self.app.query_one(LibraryTab).show_inspector_tab("info")
            return

        if event.button.id and event.button.id.startswith("ctx-"):
            action = event.button.id.replace("ctx-", "")
            lib_tab = self.app.query_one(LibraryTab)

            if action == "preview": lib_tab.action_preview()
            elif action == "make_beat": lib_tab.action_make_beat()
            elif action == "make_sample": lib_tab.action_make_sample()
            elif action == "downgrade": lib_tab.action_downgrade_beat()
            elif action == "link_asset": lib_tab.action_link_asset()
            elif action == "add_master": lib_tab.action_add_master()
            elif action == "convert_mp3": lib_tab.action_convert_mp3()
            elif action == "manage_collection": lib_tab.action_manage_collection()
            elif action == "restore_trash": lib_tab.action_restore_trash()
            elif action == "delete": lib_tab.action_delete_asset()
class CollectionManagerOverlay(Vertical):
    """An overlay for managing collections, placed in the power column."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.asset_type = "beat"
        self.asset_ids = [] # Support multiple IDs
        self.current_collection_id = None

    def compose(self) -> ComposeResult:
        yield Label("COLLECTION MANAGER", classes="panel_title")
        with Vertical(id="col-manager-content"):
            yield Label("ASSIGN TO COLLECTION", classes="modal-section-title")
            with Vertical(classes="form-section"):
                yield Select([], id="col-select", prompt="Select Collection...")
            yield Button("SAVE ASSIGNMENT", id="btn-col-assign", variant="success", classes="integrated-btn")

            yield Label("CREATE NEW COLLECTION", classes="modal-section-title")
            with Vertical(classes="form-section"):
                yield Input(placeholder="Collection Name...", id="col-new-name")
            yield Button("CREATE & ASSIGN", id="btn-col-create", variant="primary", classes="integrated-btn")
        
        with Horizontal(id="modal-buttons"):
            yield Button("BACK TO INFO", id="btn-col-close", variant="error")

    def refresh_collections(self) -> None:
        from app.models.schemas import CollectionType
        col_type = CollectionType.BEAT if self.asset_type == 'beat' else CollectionType.SAMPLE
        cols = self.app.library_engine.state_manager.get_collections_by_type(col_type)
        options = [("None / Unassigned", "none")] + [(c['name'], c['id']) for c in cols]
        select = self.query_one("#col-select", Select)
        select.set_options(options)
        
        # Force a refresh of the select to ensure it shows the value
        if self.current_collection_id:
            select.value = self.current_collection_id
        else:
            select.value = "none"

    @on(Button.Pressed, "#btn-col-assign")
    def handle_assign(self) -> None:
        val = self.query_one("#col-select", Select).value
        if val == "none": val = None
        
        success_count = 0
        for asset_id in self.asset_ids:
            if self.app.library_engine.assign_to_collection(asset_id, val, self.asset_type):
                success_count += 1
        
        if success_count > 0:
            self.app.notify(f"Assigned {success_count} assets to collection.")
            self.app.query_one(LibraryTab).refresh_library()
            self.app.query_one(LibraryTab).show_inspector_tab("info")
        else:
            self.app.notify("Assignment failed.", severity="error")

    @on(Button.Pressed, "#btn-col-create")
    def handle_create(self) -> None:
        name = self.query_one("#col-new-name", Input).value.strip()
        if not name:
            self.app.notify("Collection name cannot be empty", severity="error")
            return
        
        from app.models.schemas import Collection, CollectionType
        col_type = CollectionType.BEAT if self.asset_type == 'beat' else CollectionType.SAMPLE
        
        # 1. Create in State
        new_col = Collection(name=name, type=col_type)
        self.app.library_engine.state_manager.add_collection(new_col.dict())
        
        # 2. Create physical folder
        self.app.library_engine.create_collection_folder(name, self.asset_type)
        
        self.app.notify(f"Collection '{name}' created.")
        self.refresh_collections()
        self.query_one("#col-select", Select).value = new_col.id
        self.query_one("#col-new-name", Input).value = ""
        # We don't auto-assign here for bulk to avoid confusion, user can click "SAVE ASSIGNMENT" now

    @on(Button.Pressed, "#btn-col-close")
    def close_overlay(self) -> None:
        self.app.query_one(LibraryTab).show_inspector_tab("info")

class ImportOverlay(Vertical):
    """A professional overlay for scanning and importing assets."""
    BINDINGS = [
        Binding("space", "toggle_selection", "Select"),
        Binding("ctrl+a", "select_all", "Select All"),
        Binding("ctrl+d", "deselect_all", "Deselect"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.found_assets = []

    def compose(self) -> ComposeResult:
        yield Label("IMPORT ASSETS", classes="panel_title")
        
        with Vertical(id="import-config"):
            with Grid(id="import-grid"):
                yield Label("Source", classes="menu-label")
                with Horizontal(id="import-path-row"):
                    yield Input(placeholder="Enter path or click 📂 to browse...", id="import-search-path")
                    yield Button("📂", id="btn-import-browse", tooltip="Select Folder")
                
                yield Label("Options", classes="menu-label")
                with Horizontal(id="import-opts-row"):
                    yield Checkbox("MOVE SOURCE", id="import-delete-source", value=False)
                    yield Checkbox("SKIP DUPES", id="import-skip-dupes", value=True)
            
            yield Button("SCAN DIRECTORY", id="btn-import-scan", variant="primary")

        yield DataTable(id="import-results-table", cursor_type="row")

        with Horizontal(id="import-footer"):
            yield Button("PREVIEW", id="btn-import-preview", variant="warning")
            yield Button("IMPORT ALL", id="btn-import-all", variant="success")
            yield Button("IMPORT SELECTED", id="btn-import-collect", variant="primary")
            yield Button("CLOSE", id="btn-import-close", variant="error")

    def on_mount(self) -> None:
        table = self.query_one("#import-results-table", DataTable)
        table.selected_rows = set()
        table.add_columns(" ", "NAME", "TYPE", "FILENAME", "STATUS")

    def action_toggle_selection(self) -> None:
        table = self.query_one("#import-results-table", DataTable)
        if table.cursor_row is not None:
            row_keys = list(table.rows.keys())
            if table.cursor_row >= len(row_keys): return
            row_key = row_keys[table.cursor_row]
            # Key is the path for import-results-table
            asset_path = str(row_key)
            if not hasattr(table, "selected_rows"): table.selected_rows = set()

            if asset_path in table.selected_rows:
                table.selected_rows.remove(asset_path)
                table.update_cell(row_key, list(table.columns.keys())[0], "[ ]")
            else:
                table.selected_rows.add(asset_path)
                table.update_cell(row_key, list(table.columns.keys())[0], "[*]")
            table.action_cursor_down()

    def action_select_all(self) -> None:
        table = self.query_one("#import-results-table", DataTable)
        if not hasattr(table, "selected_rows"): table.selected_rows = set()
        for row_key in table.rows: 
            asset_path = str(row_key)
            table.selected_rows.add(asset_path)
            table.update_cell(row_key, list(table.columns.keys())[0], "[*]")
        self.app.notify("All items selected.")

    def action_deselect_all(self) -> None:
        table = self.query_one("#import-results-table", DataTable)
        if hasattr(table, "selected_rows"):
            table.selected_rows.clear()
            for row_key in table.rows:
                table.update_cell(row_key, list(table.columns.keys())[0], "[ ]")
        self.app.notify("All items deselected.")

    @on(Button.Pressed, "#btn-import-preview")
    def handle_preview(self) -> None:
        table = self.query_one("#import-results-table", DataTable)
        if table.cursor_row is not None:
            idx = table.cursor_row
            if 0 <= idx < len(self.found_assets):
                asset_data = self.found_assets[idx]
                if asset_data['type'] == 'audio':
                    self.app.audio_engine.play_preview(asset_data['path'])
                    try:
                        self.app.query_one(LibraryTab).currently_playing_id = None
                    except: pass
                    self.app.notify(f"Playing: {os.path.basename(asset_data['path'])}")
                else:
                    self.app.notify("Only audio can be previewed", severity="warning")

    @on(Button.Pressed, "#btn-import-close")
    def close_overlay(self) -> None:
        self.app.audio_engine.stop_preview()
        self.app.query_one(LibraryTab).show_inspector_tab("info")
        self.app.action_refresh_library()

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
                self.app.notify("Invalid directory", severity="error")
                return
            
            if os.path.isfile(path):
                path = os.path.dirname(path)

            self.found_assets = self.app.library_engine.scan_for_import(path)
            table = self.query_one("#import-results-table", DataTable)
            table.clear()
            if not hasattr(table, "selected_rows"): table.selected_rows = set()
            table.selected_rows.clear()
            seen_paths = set()
            for asset in self.found_assets:
                path = asset['path']
                if path in seen_paths: continue
                seen_paths.add(path)
                
                table.add_row(
                    "[ ]",
                    asset['name'],
                    asset['type'].upper(),
                    os.path.basename(asset['path']),
                    asset.get('status', 'Ready'),
                    key=path
                )
            self.app.notify(f"Scanned {len(self.found_assets)} items.")
        except Exception as e:
            self.app.notify(f"Scan failed: {str(e)}", severity="error")

    @on(Button.Pressed, "#btn-import-collect")
    def handle_collect(self) -> None:
        try:
            table = self.query_one("#import-results-table", DataTable)
            selected_indices = []
            selected_paths = getattr(table, "selected_rows", set())
            
            if selected_paths:
                # We need indices to look up in self.found_assets
                row_keys = list(table.rows.keys())
                for path in selected_paths:
                    try:
                        # RowKey is based on path, so this should work
                        from textual.widgets._data_table import RowKey
                        key = RowKey(path)
                        idx = row_keys.index(key)
                        selected_indices.append(idx)
                    except ValueError: pass
            elif table.cursor_row is not None:
                selected_indices = [table.cursor_row]

            if not selected_indices:
                self.app.notify("No items selected", severity="warning")
                return

            delete_after = self.query_one("#import-delete-source", Checkbox).value
            skip_dupes = self.query_one("#import-skip-dupes", Checkbox).value
            
            count = 0
            for idx in selected_indices:
                if 0 <= idx < len(self.found_assets):
                    asset_data = self.found_assets[idx]
                    if skip_dupes and asset_data.get('status') == 'Exists': continue
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
            
            self.app.notify(f"Imported {count} assets.")
            self.handle_scan() 
        except Exception as e:
            self.app.notify(f"Import failed: {str(e)}", severity="error")

    @on(Button.Pressed, "#btn-import-all")
    def handle_import_all(self) -> None:
        if not self.found_assets:
            self.app.notify("Nothing to import.", severity="warning")
            return
        try:
            delete_after = self.query_one("#import-delete-source", Checkbox).value
            skip_dupes = self.query_one("#import-skip-dupes", Checkbox).value
            count = 0
            for asset_data in self.found_assets:
                if skip_dupes and asset_data.get('status') == 'Exists': continue
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
            self.app.notify(f"Bulk import finished: {count} assets.")
            self.handle_scan() 
        except Exception as e:
            self.app.notify(f"Bulk import failed: {str(e)}", severity="error")

class PathPicker(ModalScreen):
    """A professional modal for file system navigation."""
    def __init__(self, initial_path: str = os.path.expanduser("~"), **kwargs):
        super().__init__(**kwargs)
        self.initial_path = initial_path

    def compose(self) -> ComposeResult:
        with Vertical(id="picker-container"):
            yield Label("FILE SYSTEM BROWSER", classes="panel_title")
            yield DirectoryTree(self.initial_path, id="picker-tree")
            with Horizontal(id="picker-buttons"):
                yield Button("CANCEL", id="btn-picker-cancel", variant="error")
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

class WaveformDisplay(Static):
    """A responsive waveform display showing progress."""
    progress = reactive(0.0)
    total = reactive(1.0)
    
    class SeekRequested(Message):
        def __init__(self, percentage: float) -> None:
            self.percentage = percentage
            super().__init__()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.base_data = [abs(math.sin(i / 5.0)) * 10 + random.random() * 5 for i in range(100)]
        
    def render(self) -> RenderResult:
        from rich.text import Text
        if not self.base_data: return Text("")
        
        bars = "  ▂▃▄▅▆▇█"
        max_val = max(self.base_data) if max(self.base_data) > 0 else 1
        normalized = [int((v / max_val) * 8) for v in self.base_data]
        
        width = self.size.width if self.size.width > 0 else len(self.base_data)
        if width == 0: width = 100
        
        resampled = []
        for i in range(width):
            idx = int(i * len(normalized) / width)
            resampled.append(normalized[min(idx, len(normalized)-1)])
        
        percentage = self.progress / self.total if self.total > 0 else 0
        split_idx = int(percentage * width)
        
        text = Text()
        for i, val in enumerate(resampled):
            char = bars[min(val, len(bars)-1)]
            style = "#91abec" if i <= split_idx else "#333f62"
            text.append(char, style=style)
            
        return text

    def on_click(self, event: events.Click) -> None:
        if self.total > 0:
            percentage = event.x / self.size.width
            self.post_message(self.SeekRequested(percentage))

    def update_data(self, data: List[float]) -> None:
        self.base_data = data
        self.refresh()

class Player(Horizontal):
    """Professional audio transport controls."""
    def compose(self) -> ComposeResult:
        yield Button("PLAY", id="btn-player-play", variant="success")
        yield Button("STOP", id="btn-player-stop", variant="error")
        yield Label("00:00", id="audio-time-current")
        yield WaveformDisplay(id="audio-waveform")
        yield Label("00:00", id="audio-time-total")

    def on_mount(self) -> None:
        self.set_interval(0.5, self.update_player)

    def _format_time(self, seconds: float) -> str:
        mins, secs = int(seconds // 60), int(seconds % 60)
        return f"{mins:02}:{secs:02}"

    def update_player(self) -> None:
        try:
            player = self.app.audio_engine.player
            pos, dur = player.get_current_position(), player.duration
            bar = self.query_one("#audio-waveform", WaveformDisplay)
            bar.total = dur if dur > 0 else 1.0
            bar.progress = pos
            self.query_one("#audio-time-current", Label).update(self._format_time(pos))
            self.query_one("#audio-time-total", Label).update(self._format_time(dur))
            
            if not player.is_playing:
                try:
                    lib_tab = self.app.query_one(LibraryTab)
                    if lib_tab.currently_playing_id is not None:
                        lib_tab.currently_playing_id = None
                except: pass
        except: pass

    def on_waveform_display_seek_requested(self, message: WaveformDisplay.SeekRequested) -> None:
        try:
            player = self.app.audio_engine.player
            if player.duration > 0:
                target = message.percentage * player.duration
                player.play(player.current_file, start_offset=target)
        except: pass

    @on(Button.Pressed, "#btn-player-play")
    def handle_play(self) -> None:
        try:
            self.app.query_one(LibraryTab).action_preview()
        except Exception as e:
            self.app.notify(f"Playback Error: {str(e)}", severity="error")

    @on(Button.Pressed, "#btn-player-stop")
    def handle_stop(self) -> None:
        self.app.audio_engine.stop_preview()
        try:
            self.app.query_one(LibraryTab).currently_playing_id = None
        except: pass

class LibraryTab(Vertical):
    currently_playing_id = reactive(None)
    asset_type_filter = reactive("all")

    BINDINGS = [
        Binding("p", "preview", "Preview"),
        Binding("s", "stop", "Stop"),
        Binding("b", "make_beat", "Make Beat"),
        Binding("u", "make_sample", "Make Sample"),
        Binding("e", "export_beat", "Export"),
        Binding("v", "move_beat", "Move"),
        Binding("f2", "rename_asset", "Rename"),
        Binding("delete", "delete_asset", "Delete"),
        Binding("ctrl+a", "select_all", "Select All"),
        Binding("ctrl+d", "deselect_all", "Deselect"),
        Binding("f5", "sync_library", "Sync"),
        Binding("l", "link_asset", "Link"),
        Binding("m", "manage_collection", "Collection"),
        Binding("d", "downgrade_beat", "Downgrade"),
        Binding("escape", "cancel_edit", "Cancel Edit", show=False),
        Binding("space", "toggle_selection", "Select"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.editing_coordinate = None
        self.editing_field = None
        self.editing_asset_id = None
        self.assets = []

    def compose(self) -> ComposeResult:
        with Vertical(id="library-header"):
            with Horizontal(id="lib-header-row-2"):
                yield Tabs(
                    Tab("ALL", id="tab-all"),
                    Tab("BEATS", id="tab-beat"),
                    Tab("SAMPLES", id="tab-sample"),
                    Tab("RAW", id="tab-raw"),
                    Tab("IMAGES", id="tab-cover"),
                    id="lib-asset-tabs"
                )
                
            with Horizontal(id="lib-header-row-1"):
                yield Input(placeholder="Search assets...", id="lib-filter-search")
                yield Button("📥", id="btn-header-import", classes="header-icon-btn")
                yield Button("📤", id="btn-header-export", classes="header-icon-btn")
                yield Button("📂", id="btn-header-move", classes="header-icon-btn")
                yield Button("🔄", id="btn-header-sync", classes="header-icon-btn")
                yield Button("🧹", id="btn-header-empty-trash", classes="header-icon-btn")
                yield Button("EDIT", id="btn-header-edit", classes="header-action-btn")
        
        with Vertical(id="library-main-content"):
            with Horizontal(id="library-body-split"):
                with Vertical(id="library-table-container"):
                    yield DataTable(id="library-table", cursor_type="row")
                    yield Input(id="inline-editor", classes="hidden")
                    yield Player(id="library-player")
                with Vertical(id="library-inspector"):
                    with Vertical(id="inspector-info-view"):
                        yield Label("ASSET INFO", classes="panel_title")
                        with TabbedContent(id="inspector-tabs"):
                            with TabPane("NOTES", id="tab-notes"):
                                yield TextArea(id="inspector-notes")
                            with TabPane("METADATA", id="tab-metadata"):
                                with VerticalScroll():
                                    with Grid(id="meta-grid"):
                                        yield Label("Genre")
                                        yield Input(id="meta-genre")
                                        yield Label("Mood")
                                        yield Input(id="meta-mood")
                                        yield Label("Key")
                                        yield Input(id="meta-key")
                                        yield Label("BPM")
                                        yield Input(id="meta-bpm")
                        yield Button("SAVE", id="btn-inspector-save", variant="success")
                    yield CollectionManagerOverlay(id="inspector-col-view", classes="hidden")
                    yield ImportOverlay(id="inspector-import-view", classes="hidden")
                    yield ActionMenuOverlay(id="inspector-action-view", classes="hidden")

    def show_inspector_tab(self, view: str) -> None:
        info_view = self.query_one("#inspector-info-view")
        col_view = self.query_one("#inspector-col-view")
        import_view = self.query_one("#inspector-import-view")
        action_view = self.query_one("#inspector-action-view")
        
        # Hide all first
        for v in [info_view, col_view, import_view, action_view]:
            v.add_class("hidden")
            
        if view == "info":
            info_view.remove_class("hidden")
        elif view == "collection":
            col_view.remove_class("hidden")
            col_view.refresh_collections()
        elif view == "import":
            import_view.remove_class("hidden")
        elif view == "action":
            action_view.remove_class("hidden")

    def on_mount(self) -> None:
        table = self.query_one("#library-table", DataTable)
        table.selected_rows = set()
        
        # Add columns with specific initial widths; DataTable columns are resizable by default in modern Textual
        table.add_column(" ", width=3)
        table.add_column("ID", width=10)
        table.add_column("NAME", width=20) # Much shorter initial width
        table.add_column("COLLECTION", width=15)
        table.add_column("TYPE", width=10)
        table.add_column("DATA", width=10)
        table.add_column("BPM", width=6)
        table.add_column("KEY", width=6)
        table.add_column("DURATION", width=10)
        
        self.library_engine = LibraryManagerEngine()
        self.populate_inspector(None)
        self.refresh_library()
        self.show_inspector_tab("info")

    @on(Input.Submitted, "#inline-editor")
    def handle_inline_edit_submit(self, event: Input.Submitted) -> None:
        new_val = event.value
        self.query_one("#inline-editor", Input).add_class("hidden")
        self.query_one("#library-table", DataTable).focus()
        if not self.editing_asset_id: return
        try:
            if self.editing_field == "name": self.library_engine.rename_asset(self.editing_asset_id, new_val)
            else:
                val = float(new_val) if self.editing_field == "bpm" and new_val.strip() else new_val
                self.library_engine.update_asset(self.editing_asset_id, {self.editing_field: val})
            self.refresh_library()
        except: self.app.notify("Database update failed", severity="error")
        self.editing_asset_id = None

    def action_cancel_edit(self) -> None:
        inp = self.query_one("#inline-editor", Input)
        if not inp.has_class("hidden"):
            inp.add_class("hidden")
            self.query_one("#library-table", DataTable).focus()
            self.editing_asset_id = None

    def watch_currently_playing_id(self, value: str | None) -> None:
        try:
            waveform = self.query_one("#audio-waveform", WaveformDisplay)
            if value is not None:
                # Generate new dummy waveform for visual variety
                new_data = [abs(math.sin(i / random.uniform(3.0, 8.0))) * 10 + random.random() * 5 for i in range(100)]
                waveform.update_data(new_data)
        except: pass
        self.refresh_library()

    def watch_asset_type_filter(self, val: str) -> None:
        self.refresh_library()

    def refresh_library(self, search: str | None = None, type_filter: str | None = None, force: bool = False) -> None:
        try:
            table = self.query_one("#library-table", DataTable)
            if search is None:
                search = self.query_one("#lib-filter-search", Input).value
                type_filter = self.asset_type_filter
            
            all_assets = self.library_engine.get_assets()
            new_assets = [
                a for a in all_assets 
                if (type_filter == "all" or a.get('asset_type', a.get('type', 'raw')) == type_filter) 
                and (not search or search.lower() in a.get('name', '').lower())
            ]
            
            # Optimization: Only rebuild if assets changed or forced
            current_ids = [str(a.get('id')) for a in getattr(self, 'assets', [])]
            new_ids = [str(a.get('id')) for a in new_assets]
            
            if not force and current_ids == new_ids and not self.currently_playing_id:
                # Still check markers in case selection changed externally
                return

            self.assets = new_assets
            
            # Save cursor state
            old_cursor_row = table.cursor_row
            
            table.clear(columns=False)
            seen_ids = set()
            selected_ids = getattr(table, "selected_rows", set())
            
            for a in self.assets:
                asset_id = str(a.get('id'))
                if not asset_id or asset_id in seen_ids:
                    continue
                seen_ids.add(asset_id)
                
                marker = "[*]" if asset_id in selected_ids else "[ ]"
                raw_name = a.get('name', 'Unknown')
                display_name = f"[bold green]▶ {raw_name}[/bold green]" if asset_id == self.currently_playing_id else raw_name
                
                col_id = a.get('collection_id')
                col_name = "Unassigned"
                if col_id:
                    col_obj = self.library_engine.state_manager.collections_table.get(Query().id == col_id)
                    if col_obj:
                        col_name = col_obj.get('name', 'Unassigned')

                try:
                    # Use a prefixed key to avoid collisions with any internal Textual keys
                    row_key = f"row_{asset_id}"
                    table.add_row(
                        marker,
                        asset_id,
                        display_name,
                        col_name,
                        a.get('asset_type', 'N/A').upper(),
                        a.get('data_type', 'AUDIO').upper(),
                        str(a.get('bpm', '') or ""),
                        str(a.get('key', '') or ""),
                        f"{a.get('duration', 0):.1f}s" if a.get('duration') else "N/A",
                        key=row_key
                    )
                except Exception as e:
                    continue
                
            # Restore cursor state
            if old_cursor_row is not None and len(self.assets) > 0:
                try:
                    table.cursor_coordinate = Coordinate(min(old_cursor_row, len(self.assets) - 1), 0)
                except: pass
            
            if len(self.assets) == 0:
                self.populate_inspector(None)
        except Exception as e:
            pass

    @on(Button.Pressed, "#btn-header-import")
    def handle_header_import(self) -> None: self.app.action_toggle_import()
    
    @on(Button.Pressed, "#btn-header-export")
    def handle_header_export(self) -> None: self.action_export_beat()
    
    @on(Button.Pressed, "#btn-header-move")
    def handle_header_move(self) -> None: self.action_move_beat()
    
    @on(Button.Pressed, "#btn-header-sync")
    def handle_header_sync(self) -> None: self.action_sync_library()
    
    @on(Button.Pressed, "#btn-header-empty-trash")
    def handle_header_empty_trash(self) -> None: self.action_empty_trash()

    @on(Button.Pressed, "#btn-header-edit")
    def handle_header_edit(self) -> None:
        self.trigger_context_menu()

    def trigger_context_menu(self) -> None:
        ids = self._get_selected_ids()
        if not ids: 
            self.app.notify("Select an asset first", severity="warning")
            return
        
        actions = [
            ("PREVIEW [P]", "preview"),
            ("MAKE BEAT [B]", "make_beat"),
            ("MAKE SAMPLE [U]", "make_sample"),
            ("DOWNGRADE [D]", "downgrade"),
            ("LINK ASSET [L]", "link_asset"),
            ("ADD MASTER", "add_master"),
            ("CONVERT TO MP3", "convert_mp3"),
            ("COLLECTION [M]", "manage_collection"),
            ("RESTORE TRASH", "restore_trash"),
            ("DELETE [DEL]", "delete")
        ]
        
        action_view = self.query_one("#inspector-action-view", ActionMenuOverlay)
        action_view.set_actions(actions)
        self.show_inspector_tab("action")
    @on(events.MouseDown, "#library-table")
    def handle_right_click(self, event: events.MouseDown) -> None:
        if event.button == 3: # Right click
            self.trigger_context_menu()

    @on(Input.Changed, "#lib-filter-search")
    def handle_filters_changed(self) -> None:
        # Debounce search
        if hasattr(self, "_search_timer"):
            self._search_timer.stop()
        self._search_timer = self.set_timer(0.3, self.refresh_library)

    @on(Tabs.TabActivated, "#lib-asset-tabs")
    def handle_asset_tab_changed(self, event: Tabs.TabActivated) -> None:
        if event.tab:
            new_filter = str(event.tab.id).replace("tab-", "")
            if new_filter != self.asset_type_filter:
                self.asset_type_filter = new_filter
                # Force refresh on tab change
                self.refresh_library(force=True)

    @on(DataTable.RowSelected, "#library-table")
    def handle_row_selected(self, event: DataTable.RowSelected) -> None:
        row_key = event.row_key.value
        asset_id = str(row_key).replace("row_", "")
        self.populate_inspector(asset_id)
        
    def populate_inspector(self, asset_id: str | None) -> None:
        self.show_inspector_tab("info")
        inspector = self.query_one("#inspector-info-view")
        notes_area = self.query_one("#inspector-notes", TextArea)
        
        if not asset_id:
            notes_area.text = ""
            self.query_one("#meta-genre", Input).value = ""
            self.query_one("#meta-mood", Input).value = ""
            self.query_one("#meta-key", Input).value = ""
            self.query_one("#meta-bpm", Input).value = ""
            if hasattr(inspector, 'asset_id'): del inspector.asset_id
            return

        asset = next((a for a in self.library_engine.get_assets() if str(a.get('id')) == asset_id), None)
        if not asset:
            self.populate_inspector(None)
            return
        
        # Load notes
        notes_path = ""
        if asset.get('asset_type') == 'beat':
            notes_path = os.path.join(asset.get('path', ''), asset.get('notes_file', 'notes.txt'))
        elif asset.get('asset_type') == 'raw':
            notes_path = os.path.join(self.library_engine.audio_dir, asset.get('notes_file', 'notes.txt'))
            
        if os.path.exists(notes_path):
            try:
                with open(notes_path, "r") as f:
                    notes_area.text = f.read()
            except Exception:
                notes_area.text = ""
        else:
            notes_area.text = ""
            
        # Load metadata
        meta = asset.get('metadata', {})
        if asset.get('asset_type') == 'beat':
            meta_json_path = os.path.join(asset.get('path', ''), "metadata.json")
            if os.path.exists(meta_json_path):
                import json
                try:
                    with open(meta_json_path, "r") as f:
                        loaded_meta = json.load(f)
                        meta.update(loaded_meta)
                except: pass
                    
        self.query_one("#meta-genre", Input).value = str(meta.get("genre", ""))
        self.query_one("#meta-mood", Input).value = str(meta.get("mood", ""))
        
        self.query_one("#meta-key", Input).value = str(meta.get("key", asset.get("key", "")))
        self.query_one("#meta-bpm", Input).value = str(meta.get("bpm", asset.get("bpm", "")))
        
        inspector.asset_id = asset_id

    @on(Button.Pressed, "#btn-inspector-save")
    def handle_inspector_save(self) -> None:
        inspector = self.query_one("#inspector-info-view")
        if not hasattr(inspector, 'asset_id'): return
        
        asset_id = inspector.asset_id
        asset = next((a for a in self.library_engine.get_assets() if str(a.get('id')) == asset_id), None)
        if not asset: return
        
        # Save notes
        notes_text = self.query_one("#inspector-notes", TextArea).text
        notes_path = ""
        if asset.get('asset_type') == 'beat':
            notes_path = os.path.join(asset.get('path', ''), asset.get('notes_file', 'notes.txt'))
        elif asset.get('asset_type') == 'raw':
            notes_path = os.path.join(self.library_engine.audio_dir, asset.get('notes_file', 'notes.txt'))
            
        if notes_path:
            try:
                with open(notes_path, "w") as f:
                    f.write(notes_text)
            except Exception as e:
                self.app.notify(f"Failed to save notes: {e}", severity="error")
                
        # Save metadata
        genre = self.query_one("#meta-genre", Input).value
        mood = self.query_one("#meta-mood", Input).value
        key = self.query_one("#meta-key", Input).value
        bpm_str = self.query_one("#meta-bpm", Input).value
        
        bpm = None
        if bpm_str:
            try: bpm = float(bpm_str)
            except: pass
            
        meta_updates = {"genre": genre, "mood": mood}
        if key: meta_updates["key"] = key
        if bpm is not None: meta_updates["bpm"] = bpm
        
        if asset.get('asset_type') == 'beat':
            meta_json_path = os.path.join(asset.get('path', ''), "metadata.json")
            import json
            current_meta = {}
            if os.path.exists(meta_json_path):
                try:
                    with open(meta_json_path, "r") as f:
                        current_meta = json.load(f)
                except: pass
                
            current_meta.update(meta_updates)
            try:
                with open(meta_json_path, "w") as f:
                    json.dump(current_meta, f)
            except Exception as e:
                self.app.notify(f"Failed to save metadata.json: {e}", severity="error")
                
            # Update DB metadata and top-level fields
            db_meta = asset.get('metadata', {})
            db_meta.update(current_meta)
            update_payload = {"metadata": db_meta}
            if key: update_payload["key"] = key
            if bpm is not None: update_payload["bpm"] = bpm
            self.library_engine.update_asset(asset_id, update_payload)
        else:
            current_meta = asset.get('metadata', {})
            current_meta.update(meta_updates)
            update_payload = {"metadata": current_meta}
            if key: update_payload["key"] = key
            if bpm is not None: update_payload["bpm"] = bpm
            self.library_engine.update_asset(asset_id, update_payload)
            
        self.app.notify("Saved notes and metadata.", severity="information")
        self.refresh_library()

    def action_toggle_selection(self) -> None:
        table = self.query_one("#library-table", DataTable)
        if table.cursor_row is not None:
            row_keys = list(table.rows.keys())
            if table.cursor_row >= len(row_keys): return
            row_key = row_keys[table.cursor_row]
            asset_id = str(row_key.value).replace("row_", "")
            
            if not hasattr(table, "selected_rows"): table.selected_rows = set()

            if asset_id in table.selected_rows:
                table.selected_rows.remove(asset_id)
                table.update_cell(row_key, list(table.columns.keys())[0], "[ ]")
            else:
                table.selected_rows.add(asset_id)
                table.update_cell(row_key, list(table.columns.keys())[0], "[*]")
            table.action_cursor_down()

    def _get_selected_ids(self) -> List[str]:
        try:
            table = self.query_one("#library-table", DataTable)
            selected_rows = getattr(table, "selected_rows", set())
            if selected_rows:
                return list(selected_rows)
            if table.cursor_row is not None:
                row_keys = list(table.rows.keys())
                if 0 <= table.cursor_row < len(row_keys):
                    return [str(table.get_row(row_keys[table.cursor_row])[1])]
        except: pass
        return []

    def action_add_master(self) -> None:
        ids = self._get_selected_ids()
        if not ids: return self.app.notify("No assets selected", severity="warning")
        
        def on_path_selected(path: str | None) -> None:
            if path:
                count = 0
                for beat_id in ids:
                    if self.library_engine.add_master_version(beat_id, path):
                        count += 1
                if count > 0:
                    self.app.notify(f"Added master version to {count} beats.")
                    self.refresh_library()
        
        self.app.push_screen(PathPicker(), on_path_selected)

    def action_convert_mp3(self) -> None:
        ids = self._get_selected_ids()
        if not ids: return self.app.notify("No assets selected", severity="warning")
        
        count = 0
        for asset_id in ids:
            try:
                if self.library_engine.generate_mp3_for_beat(asset_id):
                    count += 1
            except Exception as e:
                self.app.notify(f"MP3 generation failed for {asset_id}: {str(e)}", severity="error")
                continue
        if count > 0:
            self.app.notify(f"Generated MP3s for {count} beats.")
            self.refresh_library()

    def action_export_beat(self) -> None:
        ids = self._get_selected_ids()
        if not ids: return self.app.notify("No assets selected", severity="warning")
        
        def on_path_selected(path: str | None) -> None:
            if path:
                count = 0
                for beat_id in ids:
                    if self.library_engine.export_beat(beat_id, path):
                        count += 1
                if count > 0:
                    self.app.notify(f"Exported {count} beats to {path}")
        
        self.app.push_screen(PathPicker(), on_path_selected)

    def action_move_beat(self) -> None:
        ids = self._get_selected_ids()
        if not ids: return self.app.notify("No assets selected", severity="warning")
        
        table = self.query_one("#library-table", DataTable)
        if hasattr(table, "selected_rows"): table.selected_rows.clear()

        def on_path_selected(path: str | None) -> None:
            if path:
                count = 0
                for beat_id in ids:
                    if self.library_engine.move_beat(beat_id, path):
                        count += 1
                if count > 0:
                    self.app.notify(f"Moved {count} assets.")
                    self.refresh_library()
        
        self.app.push_screen(PathPicker(), on_path_selected)

    def action_preview(self) -> None:
        ids = self._get_selected_ids()
        if not ids:
            self.app.notify("Select an asset to preview", severity="warning")
            return
        
        asset_id = ids[0]
        asset = next((a for a in self.assets if str(a.get('id')) == asset_id), None)
        if not asset:
            asset = next((a for a in self.library_engine.get_assets() if str(a.get('id')) == asset_id), None)

        if asset:
            if asset.get('data_type') != 'audio':
                self.app.notify("Preview available for audio only", severity="warning")
                return
            
            asset_type = asset.get('asset_type', asset.get('type', 'raw'))
            audio_path = asset.get('path', '') if asset_type == 'raw' else os.path.join(asset.get('path', ''), asset.get('versions', {}).get('main', asset.get('audio_file', '')))
            
            if audio_path and os.path.exists(audio_path):
                self.app.audio_engine.play_preview(audio_path)
                self.currently_playing_id = asset_id
                self.app.notify(f"Playing: {asset.get('name', 'Unknown')}")
            else: 
                self.app.notify(f"File not found: {audio_path}", severity="error")

    def action_make_beat(self) -> None:
        ids = self._get_selected_ids()
        if not ids: return self.app.notify("No assets selected", severity="warning")
        
        table = self.query_one("#library-table", DataTable)
        if hasattr(table, "selected_rows"): table.selected_rows.clear()
        
        count = 0
        for asset_id in ids:
            try:
                self.library_engine.create_beat_from_audio(asset_id)
                count += 1
            except Exception as e:
                self.app.notify(f"Beat creation failed for {asset_id}: {str(e)}", severity="error")
                continue
        if count > 0:
            self.app.notify(f"Created {count} beat structures.")
            self.refresh_library()

    def action_make_sample(self) -> None:
        ids = self._get_selected_ids()
        if not ids: return self.app.notify("No assets selected", severity="warning")

        table = self.query_one("#library-table", DataTable)
        if hasattr(table, "selected_rows"): table.selected_rows.clear()

        count = 0
        for asset_id in ids:
            try:
                self.library_engine.create_sample_from_audio(asset_id)
                count += 1
            except Exception as e:
                self.app.notify(f"Sample creation failed for {asset_id}: {str(e)}", severity="error")
                continue
        if count > 0:
            self.app.notify(f"Created {count} sample assets.")
            self.refresh_library()

    def action_downgrade_beat(self) -> None:
        ids = self._get_selected_ids()
        if not ids: return self.app.notify("No assets selected", severity="warning")
        
        table = self.query_one("#library-table", DataTable)
        if hasattr(table, "selected_rows"): table.selected_rows.clear()
        
        count = 0
        for asset_id in ids:
            try:
                self.library_engine.downgrade_beat_to_raw(asset_id)
                count += 1
            except Exception as e:
                self.app.notify(f"Downgrade failed for {asset_id}: {str(e)}", severity="error")
                continue
        if count > 0:
            self.app.notify(f"Downgraded {count} beats to raw audio.")
            self.refresh_library()

    def action_empty_trash(self) -> None:
        def on_confirm(confirmed: bool) -> None:
            if confirmed:
                count = self.library_engine.empty_trash()
                self.app.notify(f"Trash emptied: {count} items removed.")
        self.app.push_screen(ConfirmModal("Are you sure? This will permanently delete all files in the trash."), on_confirm)

    def action_manage_collection(self) -> None:
        ids = self._get_selected_ids()
        if not ids: return self.app.notify("Select assets to manage their collection", severity="warning")
        
        # Determine shared type and current collection
        assets = [a for a in self.library_engine.get_assets() if str(a.get('id')) in ids]
        if not assets: return
        
        # Use type of first selected
        a_type = assets[0].get('asset_type', assets[0].get('type', 'raw'))
        if a_type not in ['beat', 'sample']:
            return self.app.notify("Collections only apply to Beats and Samples.", severity="warning")
            
        col_view = self.query_one("#inspector-col-view")
        col_view.asset_ids = ids
        col_view.asset_type = a_type
        # If single item, show its current collection
        col_view.current_collection_id = assets[0].get('collection_id') if len(ids) == 1 else None
        
        self.show_inspector_tab("collection")

    def action_restore_trash(self) -> None:
        ids = self._get_selected_ids()
        if not ids: return self.app.notify("Select a BEAT to restore to.", severity="warning")
        
        target_id = ids[0]
        asset = next((a for a in self.library_engine.get_assets() if str(a.get('id')) == target_id), None)
        if not asset or asset.get('asset_type') != AssetType.BEAT:
            return self.app.notify("Please select a BEAT asset as the target.", severity="error")
            
        trash_dir = self.library_engine.trash_dir
        if not os.path.exists(trash_dir):
            return self.app.notify("Trash is empty.", severity="warning")
            
        trash_items = [item for item in os.listdir(trash_dir) if os.path.isdir(os.path.join(trash_dir, item))]
        if not trash_items:
            return self.app.notify("Trash is empty.", severity="warning")
            
        def on_trash_selected(trash_name: str | None) -> None:
            if trash_name:
                try:
                    self.library_engine.restore_from_trash(trash_name, target_id)
                    self.app.notify(f"Restored beat state for {asset['name']}")
                    self.refresh_library()
                except Exception as e:
                    self.app.notify(f"Restore failed: {str(e)}", severity="error")
                    self.refresh_library()
                    
        self.app.push_screen(TrashPicker(trash_items), on_trash_selected)

    def action_link_asset(self) -> None:
        ids = self._get_selected_ids()
        selected = [a for a in self.library_engine.get_assets() if str(a.get('id')) in ids]
        beats = [a for a in selected if a.get('asset_type') == 'beat']
        others = [a for a in selected if a.get('asset_type') != 'beat']
        
        if not beats or not others: 
            return self.app.notify("Select one BEAT and at least one other asset to link.", severity="warning")
            
        beat_id = beats[0]['id']
        linked_count = 0
        
        for other in others:
            role = "linked"
            if other.get('data_type') == 'image': role = "cover"
            elif other.get('asset_type') == 'raw': role = "source"
            
            # Update linked_assets dict
            beat_doc = next((a for a in self.library_engine.get_assets() if a['id'] == beat_id), None)
            if beat_doc:
                linked = beat_doc.get('linked_assets', {})
                linked[role] = other['id']
                updates = {'linked_assets': linked}
                if role == "cover": updates['cover_image_id'] = other['id'] # Keep legacy field in sync
                
                if self.library_engine.update_asset(beat_id, updates):
                    linked_count += 1
        
        if linked_count > 0:
            self.app.notify(f"Linked {linked_count} assets to {beats[0]['name']}")
            self.refresh_library()

    def action_rename_asset(self) -> None:
        try:
            table = self.query_one("#library-table", DataTable)
            if table.cursor_row is not None:
                row_keys = list(table.rows.keys())
                if table.cursor_row >= len(row_keys): return
                row_key = row_keys[table.cursor_row]
                row_data = table.get_row(row_key)
                asset_id = str(row_key.value).replace("row_", "")
                asset = next((a for a in self.assets if str(a.get('id')) == asset_id), None)
                if not asset: return

                col_idx = 2 # NAME column
                field_name = "name"
                current_val = asset.get(field_name, "") or ""

                inp = self.query_one("#inline-editor", Input)
                from textual.coordinate import Coordinate
                region = table._get_cell_region(Coordinate(table.cursor_row, col_idx))
                y_offset = region.y - table.scroll_offset.y
                x_offset = region.x - table.scroll_offset.x
                if y_offset < 0 or y_offset >= table.size.height: return
                inp.styles.offset, inp.styles.width = (x_offset, y_offset), region.width
                inp.value, self.editing_field, self.editing_asset_id = str(current_val), field_name, asset_id
                inp.remove_class("hidden")
                inp.focus()
        except: pass

    def action_delete_asset(self) -> None:
        ids = self._get_selected_ids()
        if not ids: return self.app.notify("No assets selected", severity="warning")
        table = self.query_one("#library-table", DataTable)
        if hasattr(table, "selected_rows"): table.selected_rows.clear()
        deleted_count = 0
        for asset_id in ids:
            if self.library_engine.delete_asset(asset_id): deleted_count += 1
        if deleted_count > 0:
            self.app.notify(f"Removed {deleted_count} assets from library.")
            self.refresh_library()

    def action_sync_library(self) -> None:
        self.app.notify("Synchronizing with disk...")
        removed = self.library_engine.sync_library_with_disk()
        if removed > 0: self.app.notify(f"Cleaned {removed} missing files.", severity="warning")
        else: self.app.notify("Library is synchronized.")
        self.refresh_library()

    def action_select_all(self) -> None:
        table = self.query_one("#library-table", DataTable)
        if not hasattr(table, "selected_rows"): table.selected_rows = set()
        for row_key in table.rows: 
            asset_id = str(row_key.value).replace("row_", "")
            table.selected_rows.add(asset_id)
            table.update_cell(row_key, list(table.columns.keys())[0], "[*]")
        self.app.notify("All items selected.")

    def action_deselect_all(self) -> None:
        table = self.query_one("#library-table", DataTable)
        if hasattr(table, "selected_rows"):
            table.selected_rows.clear()
            for row_key in table.rows:
                table.update_cell(row_key, list(table.columns.keys())[0], "[ ]")
        self.app.notify("All items deselected.")

    def action_stop(self) -> None:
        self.app.audio_engine.stop_preview()
        self.currently_playing_id = None
        self.app.notify("Playback stopped.")

class YoutubeTab(Vertical):
    def compose(self) -> ComposeResult:
        with Horizontal(id="yt-row"):
            with Vertical(id="yt-left"):
                yield Label("UPLOAD HISTORY", classes="panel_title")
                yield DataTable(id="yt-uploads-table", cursor_type="row")
                with Horizontal(id="yt-left-footer"):
                    yield Button("REFRESH", id="btn-yt-refresh")
                    yield Button("DELETE", id="btn-yt-delete", variant="error")

            with VerticalScroll(id="yt-right"):
                yield Label("YOUTUBE PUBLISHING", classes="panel_title")

                with Horizontal(classes="yt-form-row"):
                    yield Label("Video", classes="menu-label")
                    yield Input(placeholder="/path/to/video.mp4", id="yt-video", value=os.path.join(BASE_DIR, "output.mp4"))

                with Horizontal(classes="yt-form-row"):
                    yield Label("Thumb", classes="menu-label")
                    yield Input(placeholder="/path/to/thumb.jpg", id="yt-thumb")

                with Horizontal(classes="yt-form-row"):
                    yield Label("Title", classes="menu-label")
                    yield Input(placeholder="Enter title...", id="yt-title")

                with Vertical(id="yt-desc-container"):
                    yield Label("Description", classes="menu-label")
                    yield TextArea(id="yt-desc")

                with Horizontal(classes="yt-form-row"):
                    yield Label("Tags", classes="menu-label")
                    yield Input(placeholder="music, beat, hiphop...", id="yt-tags")

                with Horizontal(classes="yt-form-row"):
                    yield Label("Category", classes="menu-label")
                    yield Select([("Music", "10"), ("Entertainment", "24")], id="yt-cat", value="10")

                with Horizontal(classes="yt-form-row"):
                    yield Label("Privacy", classes="menu-label")
                    yield Select([("Private", "private"), ("Unlisted", "unlisted"), ("Public", "public")], id="yt-privacy", value="private")

                with Horizontal(classes="yt-form-row"):
                    yield Label("Schedule", classes="menu-label")
                    yield Input(placeholder="2024-01-01T12:00:00Z", id="yt-schedule")

                with Horizontal(id="yt-right-footer"):
                    yield Button("SAVE DRAFT", id="btn-yt-save-draft")
                    yield Button("UPLOAD NOW", id="btn-yt-upload", variant="primary")
    def on_mount(self) -> None:
        table = self.query_one("#yt-uploads-table", DataTable)
        table.add_columns("ID", "TITLE", "STATUS", "DATE")
        self.refresh_table()

    def refresh_table(self) -> None:
        try:
            table = self.query_one("#yt-uploads-table", DataTable)
            table.clear()
            uploads = StateManager(STATE_JSON).get_yt_uploads()
            for u in uploads:
                table.add_row(
                    u.get('id', 'N/A'),
                    u.get('title', 'Untitled'),
                    u.get('status', 'draft').upper(),
                    u.get('publish_at', u.get('created_at', ''))[:10],
                    key=u.get('id')
                )
        except: pass

    @on(Button.Pressed, "#btn-yt-refresh")
    def handle_refresh(self) -> None:
        self.refresh_table()

    @on(Button.Pressed, "#btn-yt-delete")
    def handle_delete(self) -> None:
        try:
            table = self.query_one("#yt-uploads-table", DataTable)
            if table.cursor_row is not None:
                row_keys = list(table.rows.keys())
                if table.cursor_row < len(row_keys):
                    upload_id = row_keys[table.cursor_row]
                    StateManager(STATE_JSON).delete_yt_upload(upload_id)
                    self.refresh_table()
                    self.app.notify("Upload entry removed.")
        except: pass

class BeatManagerApp(App):
    TITLE = "BEAT MANAGER"
    CSS_PATH = "styles.tcss"
    show_import = reactive(False)
    BINDINGS = [
        Binding("q", "quit", "Quit"), 
        Binding("r", "refresh_all", "Refresh"), 
        Binding("ctrl+i", "toggle_import", "Import Panel")
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        from textual.theme import Theme as TextualTheme
        theme = TextualTheme(
            name="dolphie_theme",
            primary="white",
            variables={
                "white": "#e9e9e9", "green": "#54efae", "yellow": "#f6ff8f",
                "red": "#fd8383", "highlight": "#91abec", "label": "#c5c7d2",
                "panel_border": "#6171a6", "table_border": "#333f62",
            },
        )
        self.register_theme(theme)
        self.theme = "dolphie_theme"

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(id="main-tabs"):
            with TabPane("LIBRARY", id="pane-library"): yield LibraryTab()
            with TabPane("YOUTUBE", id="pane-youtube"): yield YoutubeTab()
        with Horizontal(id="footer-bar"):
            yield Button("IMPORT [Ctrl+I]", id="btn-toggle-import")
            yield Footer()

    def action_toggle_import(self) -> None:
        try:
            lib_tab = self.query_one(LibraryTab)
            # If already on import, go back to info, otherwise show import
            current_import = lib_tab.query_one("#inspector-import-view")
            if not current_import.has_class("hidden"):
                lib_tab.show_inspector_tab("info")
            else:
                lib_tab.show_inspector_tab("import")
        except: pass

    def watch_show_import(self, show: bool) -> None:
        pass # reactive no longer needed for global overlay
    @on(Button.Pressed, "#btn-toggle-import")
    def handle_toggle_import(self) -> None: self.action_toggle_import()

    def on_mount(self) -> None:
        self.library_engine, self.audio_engine, self.dispatcher = LibraryManagerEngine(), AudioEngine(), TaskDispatcher(BASE_DIR)
        self.notify("System Online", title="BeatManager")

    def on_error(self, error: Exception) -> None:
        import traceback
        with open("crash.log", "a") as f: f.write(f"\n[{datetime.now().isoformat()}] GLOBAL CRASH: {str(error)}\n{traceback.format_exc()}\n")
        super().on_error(error)

    def on_unmount(self) -> None:
        if hasattr(self, "audio_engine"): self.audio_engine.stop_preview()

    def action_refresh_library(self) -> None:
        try: self.query_one(LibraryTab).refresh_library()
        except: pass

    def action_refresh_all(self) -> None: self.action_refresh_library()

if __name__ == "__main__":
    BeatManagerApp().run()