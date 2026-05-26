import os
import glob
import json
import time
import math
import random
import asyncio
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
    """An overlay for asset actions in the power column using a ListView for stability."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.actions = []

    def compose(self) -> ComposeResult:
        yield Label("ACTION MENU", classes="panel_title")
        yield ListView(id="action-menu-list")
        with Horizontal(id="modal-buttons"):
            yield Button("BACK", id="btn-action-close", variant="error")

    def set_actions(self, actions: List[Tuple[str, str]]) -> None:
        self.actions = actions
        list_view = self.query_one("#action-menu-list", ListView)
        list_view.clear()
        for label, action_id in self.actions:
            item = ListItem(Label(label))
            item.action_id = action_id # Store custom attribute
            list_view.append(item)

    @on(ListView.Selected, "#action-menu-list")
    def handle_list_selection(self, event: ListView.Selected) -> None:
        if event.item and hasattr(event.item, "action_id"):
            action = event.item.action_id
            lib_tab = self.app.query_one(LibraryTab)

            if action == "preview": lib_tab.action_preview()
            elif action == "upload_yt": lib_tab.action_upload_yt()
            elif action == "make_beat": lib_tab.action_make_beat()
            elif action == "make_song": lib_tab.action_make_song()
            elif action == "make_sample": lib_tab.action_make_sample()
            elif action == "separate_stems": lib_tab.action_separate_stems()
            elif action == "downgrade": lib_tab.action_downgrade_beat()
            elif action == "link_asset": lib_tab.action_link_asset()
            elif action == "add_master": lib_tab.action_add_master()
            elif action == "convert_mp3": lib_tab.action_convert_mp3()
            elif action == "restore_trash": lib_tab.action_restore_trash()
            elif action == "delete": lib_tab.action_delete_asset()

    @on(Button.Pressed, "#btn-action-close")
    def close_menu(self) -> None:
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

    def action_deselect_all(self) -> None:
        table = self.query_one("#import-results-table", DataTable)
        if hasattr(table, "selected_rows"):
            table.selected_rows.clear()
            for row_key in table.rows:
                table.update_cell(row_key, list(table.columns.keys())[0], "[ ]")

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
                    self.app.update_activity(f"PLAYING: {os.path.basename(asset_data['path'])}")
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
            self.app.update_activity(f"SCANNED: {len(self.found_assets)} ITEMS")
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
            
            self.app.update_activity(f"IMPORTED {count} ASSETS")
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
            self.app.update_activity(f"BULK IMPORT FINISHED: {count} ASSETS")
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
        Binding("d", "downgrade_beat", "Downgrade"),
        Binding("escape", "clear_selection", "Clear Selection"),
        Binding("slash", "focus_search", "Search"),
        Binding("i", "invert_selection", "Invert Selection"),
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
            with Horizontal(id="lib-header-row-tabs"):
                yield Tabs(
                    Tab("ALL", id="tab-all"),
                    Tab("BEATS", id="tab-beat"),
                    Tab("SONGS", id="tab-song"),
                    Tab("SAMPLES", id="tab-sample"),

                    Tab("RAW", id="tab-raw"),
                    Tab("IMAGES", id="tab-cover"),
                    id="lib-asset-tabs"
                )
            
            with Horizontal(id="lib-header-row-stats"):
                yield Label("0 ITEMS", id="lib-count-status")
                
            with Horizontal(id="lib-header-row-search"):
                yield Input(placeholder="Search assets...", id="lib-filter-search")
                yield Button("📥", id="btn-header-import", classes="header-icon-btn")
                yield Button("📤", id="btn-header-export", classes="header-icon-btn")
                yield Button("📂", id="btn-header-move", classes="header-icon-btn")
                yield Button("🔄", id="btn-header-sync", classes="header-icon-btn")
                yield Button("🧹", id="btn-header-empty-trash", classes="header-icon-btn")
                yield Button("EDIT", id="btn-header-edit", classes="header-action-btn")
        
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
                                    yield Label("Tags")
                                    yield Input(placeholder="tag1, tag2...", id="meta-tags")
                    with Vertical(id="inspector-footer"):
                        yield Label("ACTIVE AUDIO VERSION", id="lbl-audio-version")
                        with Horizontal(id="inspector-footer-row"):
                            yield Select([], id="audio-source-select", prompt="SELECT...")
                            yield Button("SAVE", id="btn-inspector-save", variant="success")

                yield ImportOverlay(id="inspector-import-view", classes="hidden")
                yield ActionMenuOverlay(id="inspector-action-view", classes="hidden")

    def show_inspector_tab(self, view: str) -> None:
        self.current_inspector_tab = view
        info_view = self.query_one("#inspector-info-view")
        import_view = self.query_one("#inspector-import-view")
        action_view = self.query_one("#inspector-action-view")
        
        # Hide all first
        for v in [info_view, import_view, action_view]:
            v.add_class("hidden")
            
        if view == "info":
            info_view.remove_class("hidden")
        elif view == "import":
            import_view.remove_class("hidden")
        elif view == "action":
            action_view.remove_class("hidden")

    def on_mount(self) -> None:
        self.current_inspector_tab = "info"
        table = self.query_one("#library-table", DataTable)
        table.selected_rows = set()
        
        # Add columns with specific initial widths; DataTable columns are resizable by default in modern Textual
        table.add_column(" ", width=3)
        table.add_column("ID", width=10)
        table.add_column("NAME", width=20) # Much shorter initial width
        table.add_column("TAGS", width=15)
        table.add_column("TYPE", width=10)
        table.add_column("DATA", width=10)
        table.add_column("BPM", width=6)
        table.add_column("KEY", width=6)
        table.add_column("DURATION", width=10)
        
        # Ensure we use the SQLite DB path
        db_path = os.path.join(BASE_DIR, "state.db")
        self.app.library_engine = LibraryManagerEngine(db_path=db_path)
        self.populate_inspector(None)
        self.refresh_library(force=True)
        self.show_inspector_tab("info")

    @on(Input.Submitted, "#inline-editor")
    def handle_inline_edit_submit(self, event: Input.Submitted) -> None:
        new_val = event.value
        self.query_one("#inline-editor", Input).add_class("hidden")
        self.query_one("#library-table", DataTable).focus()
        if not self.editing_asset_id: return
        try:
            if self.editing_field == "name": self.app.library_engine.rename_asset(self.editing_asset_id, new_val)
            else:
                val = float(new_val) if self.editing_field == "bpm" and new_val.strip() else new_val
                self.app.library_engine.update_asset(self.editing_asset_id, {self.editing_field: val})
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
            
            all_assets = self.app.library_engine.get_assets()
            
            new_assets = []
            for a in all_assets:
                # Get the effective asset type
                a_type = a.get('asset_type', a.get('type', 'raw'))
                
                # Check filter
                if type_filter != "all" and a_type != type_filter:
                    continue
                
                # Check search
                if search:
                    if search.startswith("#"):
                        target_tag = search[1:].lower().strip()
                        asset_tags = [t.lower() for t in a.get('tags', [])]
                        if not any(target_tag in t for t in asset_tags):
                            continue
                    elif search.lower() not in a.get('name', '').lower():
                        continue
                    
                new_assets.append(a)
            
            # Optimization: Only rebuild if assets changed or forced
            current_ids = [str(a.get('id')) for a in getattr(self, 'assets', [])]
            new_ids = [str(a.get('id')) for a in new_assets]
            
            if not force and current_ids == new_ids and not self.currently_playing_id:
                # Still check markers in case selection changed externally
                return

            self.assets = new_assets
            
            # Update count status
            try:
                self.query_one("#lib-count-status", Label).update(f"{len(self.assets)} ITEMS")
            except: pass
            
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
                
                tags_display = ", ".join(a.get('tags', []))

                try:
                    # Use a prefixed key to avoid collisions with any internal Textual keys
                    row_key = f"row_{asset_id}"
                    table.add_row(
                        marker,
                        asset_id,
                        display_name,
                        tags_display,
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
            
            # Restore selection state
            if selected_ids:
                table.selected_rows = set(selected_ids) # Restore as a SET
                for row_key in table.rows.keys():
                    asset_id = str(row_key.value).replace("row_", "")
                    if asset_id in table.selected_rows:
                        table.update_cell(row_key, list(table.columns.keys())[0], "[*]")

            if len(self.assets) == 0:
                self.populate_inspector(None)
        except Exception as e:
            import traceback
            with open("crash.log", "a") as f:
                f.write(f"\n[{datetime.now().isoformat()}] REFRESH ERROR: {str(e)}\n{traceback.format_exc()}\n")
            self.app.update_activity("ERROR: LIBRARY REFRESH FAILED")

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
            self.app.update_activity("ERROR: SELECT ASSETS FIRST")
            return
        
        actions = [
            ("PREVIEW [P]", "preview"),
            ("UPLOAD TO YT [Y]", "upload_yt"),
            ("MAKE BEAT [B]", "make_beat"),
            ("MAKE SONG [S]", "make_song"),
            ("MAKE SAMPLE [U]", "make_sample"),
            ("SEPARATE STEMS", "separate_stems"),
            ("DOWNGRADE [D]", "downgrade"),

            ("LINK ASSET [L]", "link_asset"),
            ("ADD MASTER", "add_master"),
            ("CONVERT TO MP3", "convert_mp3"),
            ("RESTORE TRASH", "restore_trash"),
            ("DELETE [DEL]", "delete")
        ]
        
        action_view = self.query_one("#inspector-action-view", ActionMenuOverlay)
        action_view.set_actions(actions)
        self.show_inspector_tab("action")
    @on(events.MouseDown, "DataTable")
    def handle_right_click(self, event: events.MouseDown) -> None:
        if event.button == 3: # Right click
            # If nothing is selected, try to select the row under the mouse
            # but for now, just trigger context menu for current selection
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

    @on(DataTable.RowHighlighted, "#library-table")
    def handle_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key is None: return
        
        table = self.query_one("#library-table", DataTable)
        selected_ids = list(getattr(table, "selected_rows", set()))
        
        if len(selected_ids) > 1:
            # We are in multi-select mode.
            # Only re-populate if the bulk selection has actually changed
            # (which shouldn't happen just by moving the cursor, but let's be safe)
            current_bulk = getattr(self.query_one("#inspector-info-view"), "bulk_ids", [])
            if set(selected_ids) != set(current_bulk):
                self.populate_inspector_bulk(selected_ids)
        elif len(selected_ids) == 1:
            # Single item selected - always show that item
            self.populate_inspector(selected_ids[0])
        else:
            # No selection - show the highlighted item
            row_key = event.row_key.value
            asset_id = str(row_key).replace("row_", "")
            self.populate_inspector(asset_id)
            
    def populate_inspector(self, asset_id: str | None) -> None:
        self._populating_inspector = True
        try:
            if getattr(self, "current_inspector_tab", "info") == "info":
                self.show_inspector_tab("info")
            
            inspector = self.query_one("#inspector-info-view")
            notes_area = self.query_one("#inspector-notes", TextArea)
            
            if not asset_id:
                notes_area.text = ""
                self.query_one("#meta-genre", Input).value = ""
                self.query_one("#meta-mood", Input).value = ""
                self.query_one("#meta-key", Input).value = ""
                self.query_one("#meta-bpm", Input).value = ""
                self.query_one("#meta-tags", Input).value = ""
                if hasattr(inspector, 'asset_id'): del inspector.asset_id
                if hasattr(inspector, 'bulk_ids'): del inspector.bulk_ids
                inspector.initial_values = {}
                return

            asset = self.app.library_engine.get_asset(asset_id)
            if not asset:
                self.populate_inspector(None)
                return
            
            # Resolve files
            resolved = self.app.library_engine.resolve_asset_paths(asset_id)
            
            # Load notes
            notes_path = resolved.get("notes")
            if not notes_path or not os.path.exists(notes_path):
                # Fallback to the main markdown file if no separate notes exist
                notes_path = resolved.get("markdown")

            if notes_path and os.path.exists(notes_path):
                try:
                    with open(notes_path, "r") as f:
                        notes_area.text = f.read()
                except Exception:
                    notes_area.text = ""
            else:
                notes_area.text = ""
                
            # Load metadata
            meta = asset.get('metadata', {})
            
            genre = str(meta.get("genre", ""))
            mood = str(meta.get("mood", ""))
            key = str(meta.get("key", asset.get("key", "")))
            bpm = str(meta.get("bpm", asset.get("bpm", "")))
            tags = ", ".join(resolved.get("tags", asset.get("tags", [])))

            self.query_one("#meta-genre", Input).value = genre
            self.query_one("#meta-mood", Input).value = mood
            self.query_one("#meta-key", Input).value = key
            self.query_one("#meta-bpm", Input).value = bpm
            self.query_one("#meta-tags", Input).value = tags
            
            # Update audio versions selector
            source_select = self.query_one("#audio-source-select", Select)
            audio_options = []
            
            versions = resolved.get("versions", [])
            if versions:
                for v in versions:
                    audio_options.append((v["name"], v["path"]))
            
            source_select.set_options(audio_options)
            
            # Default to the first version (usually 'Original (Raw)')
            if audio_options:
                source_select.value = audio_options[0][1]
            else:
                source_select.value = Select.BLANK

            inspector.asset_id = asset_id
            if hasattr(inspector, 'bulk_ids'): del inspector.bulk_ids
            
            # Store initial values for change detection
            inspector.initial_values = {
                "genre": genre, "mood": mood, "key": key,
                "bpm": bpm, "tags": tags, "notes": notes_area.text
            }
        finally:
            self._populating_inspector = False

    def populate_inspector_bulk(self, asset_ids: List[str]) -> None:
        """Populate inspector with multiple assets for bulk editing."""
        self._populating_inspector = True
        try:
            if getattr(self, "current_inspector_tab", "info") == "info":
                self.show_inspector_tab("info")
                
            inspector = self.query_one("#inspector-info-view")
            notes_area = self.query_one("#inspector-notes", TextArea)
            
            # Clear audio sources in bulk mode
            self.query_one("#audio-source-select", Select).set_options([])
            
            assets = []
            for aid in asset_ids:
                a = self.app.library_engine.get_asset(aid)
                if a: assets.append(a)
            
            if not assets:
                self.populate_inspector(None)
                return

            # Helper to find common value or '*'
            def get_common(keys, attr=None):
                values = []
                for a in assets:
                    val = a
                    for k in keys:
                        if isinstance(val, dict): val = val.get(k)
                        else: val = None
                    if attr and not val: # Check top level too
                        val = a.get(attr)
                    values.append(str(val or ""))
                return values[0] if all(v == values[0] for v in values) else "*"

            genre = get_common(["metadata", "genre"])
            mood = get_common(["metadata", "mood"])
            key = get_common(["metadata", "key"], "key")
            bpm = get_common(["metadata", "bpm"], "bpm")
            
            # Tags are a bit special as they are a list
            tag_sets = [set(a.get("tags", [])) for a in assets]
            common_tags = set.intersection(*tag_sets) if tag_sets else set()
            if all(ts == tag_sets[0] for ts in tag_sets):
                tags = ", ".join(sorted(list(common_tags)))
            else:
                tags = "*"

            self.query_one("#meta-genre", Input).value = genre
            self.query_one("#meta-mood", Input).value = mood
            self.query_one("#meta-key", Input).value = key
            self.query_one("#meta-bpm", Input).value = bpm
            self.query_one("#meta-tags", Input).value = tags

            notes_area.text = "[BULK EDITING - NOTES NOT SHARED]"
            
            inspector.bulk_ids = asset_ids
            if hasattr(inspector, 'asset_id'): del inspector.asset_id
            
            # Store initial values for change detection
            inspector.initial_values = {
                "genre": genre, "mood": mood, "key": key,
                "bpm": bpm, "tags": tags, "notes": notes_area.text
            }
        finally:
            self._populating_inspector = False

    @on(Select.Changed, "#audio-source-select")
    def handle_audio_source_changed(self, event: Select.Changed) -> None:
        if event.value and event.value != Select.BLANK and not getattr(self, "_populating_inspector", False):
            # Restart preview with the new source if something is already playing
            if self.currently_playing_id:
                self.action_preview()

    @on(Button.Pressed, "#btn-inspector-save")
    def handle_inspector_save(self, is_auto: bool = False) -> None:
        inspector = self.query_one("#inspector-info-view")
        
        asset_ids = []
        if hasattr(inspector, 'asset_id'):
            asset_ids = [inspector.asset_id]
        elif hasattr(inspector, 'bulk_ids'):
            asset_ids = inspector.bulk_ids
        
        if not asset_ids:
            if not is_auto: self.app.notify("No assets selected for saving", severity="warning")
            return

        # Capture current form values
        genre = self.query_one("#meta-genre", Input).value
        mood = self.query_one("#meta-mood", Input).value
        key = self.query_one("#meta-key", Input).value
        bpm_str = self.query_one("#meta-bpm", Input).value
        tags_str = self.query_one("#meta-tags", Input).value
        notes_text = self.query_one("#inspector-notes", TextArea).text

        # Get initial values to detect actual changes
        initial = getattr(inspector, "initial_values", {})
        
        changes_to_apply = {}
        if genre != initial.get("genre") and genre != "*": changes_to_apply["genre"] = genre
        if mood != initial.get("mood") and mood != "*": changes_to_apply["mood"] = mood
        if key != initial.get("key") and key != "*": changes_to_apply["key"] = key
        if bpm_str != initial.get("bpm") and bpm_str != "*": changes_to_apply["bpm"] = bpm_str
        if tags_str != initial.get("tags") and tags_str != "*": changes_to_apply["tags"] = tags_str
        
        notes_changed = (len(asset_ids) == 1 and notes_text != initial.get("notes") 
                         and notes_text != "[BULK EDITING - NOTES NOT SHARED]")

        if not changes_to_apply and not notes_changed:
            return

        # Only process notes if it's a single asset
        if notes_changed:
            asset_id = asset_ids[0]
            resolved = self.app.library_engine.resolve_asset_paths(asset_id)
            notes_path = resolved.get("notes")
            if notes_path:
                try:
                    with open(notes_path, "w") as f: f.write(notes_text)
                    initial["notes"] = notes_text # Update initial for auto-save loop
                except Exception as e:
                    if not is_auto: self.app.notify(f"Failed to save notes: {e}", severity="error")

        # Process metadata for all selected assets
        success_count = 0
        update_error = None
        
        for aid in asset_ids:
            asset = self.app.library_engine.get_asset(aid)
            if not asset: continue

            update_payload = {}
            current_meta = asset.get('metadata', {})
            if not isinstance(current_meta, dict): current_meta = {}
            new_meta = dict(current_meta)

            meta_changed = False
            if "genre" in changes_to_apply:
                new_meta["genre"] = changes_to_apply["genre"]
                meta_changed = True
            if "mood" in changes_to_apply:
                new_meta["mood"] = changes_to_apply["mood"]
                meta_changed = True
            if "key" in changes_to_apply:
                update_payload["key"] = changes_to_apply["key"]
                new_meta["key"] = changes_to_apply["key"]
                meta_changed = True
            if "bpm" in changes_to_apply:
                try:
                    val = changes_to_apply["bpm"]
                    bpm = float(val) if val.strip() else None
                    update_payload["bpm"] = bpm
                    new_meta["bpm"] = bpm
                    meta_changed = True
                except: pass

            if meta_changed:
                update_payload["metadata"] = new_meta
                
            if "tags" in changes_to_apply:
                tags = [t.strip() for t in changes_to_apply["tags"].split(",") if t.strip()]
                update_payload["tags"] = tags

            if update_payload:
                try:
                    if self.app.library_engine.update_asset(aid, update_payload):
                        success_count += 1
                    else:
                        update_error = "Database update returned False"
                except Exception as e:
                    update_error = str(e)

        if success_count > 0:
            # Update initial values so auto-save doesn't re-trigger
            for k, v in changes_to_apply.items():
                initial[k] = v
                
            if not is_auto:
                msg = f"SAVED {success_count} ASSETS" if len(asset_ids) > 1 else f"SAVED: {asset.get('name')}"
                self.app.update_activity(msg)
                self.refresh_library()
        elif not is_auto and asset_ids:
            if not changes_to_apply and not notes_changed:
                self.app.notify("No changes detected", severity="information")
            else:
                self.app.notify(f"Update failed: {update_error or 'Unknown error'}", severity="error")

    @on(Input.Changed, "#meta-genre")
    @on(Input.Changed, "#meta-mood")
    @on(Input.Changed, "#meta-key")
    @on(Input.Changed, "#meta-bpm")
    @on(Input.Changed, "#meta-tags")
    @on(TextArea.Changed, "#inspector-notes")
    def handle_auto_save(self) -> None:
        if getattr(self, "_populating_inspector", False):
            return
        self.handle_inspector_save(is_auto=True)

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
            
            # Selection changed, let RowHighlighted or manual call handle the inspector
            # However, since RowHighlighted might not trigger if the row doesn't change,
            # we force a check here.
            selected_ids = list(table.selected_rows)
            inspector = self.query_one("#inspector-info-view")
            
            if len(selected_ids) > 1:
                self.populate_inspector_bulk(selected_ids)
            elif len(selected_ids) == 1:
                self.populate_inspector(selected_ids[0])
            else:
                # Revert to highlighted row if no selection
                if table.cursor_row is not None:
                    row_keys = list(table.rows.keys())
                    current_asset_id = str(row_keys[table.cursor_row].value).replace("row_", "")
                    self.populate_inspector(current_asset_id)
            
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
        if not ids: 
            self.app.update_activity("ERROR: NO ASSETS SELECTED")
            return
        
        def on_path_selected(path: str | None) -> None:
            if path:
                count = 0
                for beat_id in ids:
                    if self.app.library_engine.add_master_version(beat_id, path):
                        count += 1
                if count > 0:
                    self.app.update_activity(f"ADDED MASTER TO {count} BEATS")
                    self.refresh_library()
        
        self.app.push_screen(PathPicker(), on_path_selected)

    def action_convert_mp3(self) -> None:
        ids = self._get_selected_ids()
        if not ids: 
            self.app.update_activity("ERROR: NO ASSETS SELECTED")
            return
        
        count = 0
        for asset_id in ids:
            try:
                if self.app.library_engine.generate_mp3_for_beat(asset_id):
                    count += 1
            except Exception as e:
                self.app.notify(f"MP3 generation failed for {asset_id}: {str(e)}", severity="error")
                continue
        if count > 0:
            self.app.update_activity(f"GENERATED MP3s FOR {count} BEATS")
            self.refresh_library()

    def action_export_beat(self) -> None:
        ids = self._get_selected_ids()
        if not ids: 
            self.app.update_activity("ERROR: NO ASSETS SELECTED")
            return
        
        def on_path_selected(path: str | None) -> None:
            if path:
                count = 0
                for beat_id in ids:
                    if self.app.library_engine.export_beat(beat_id, path):
                        count += 1
                if count > 0:
                    self.app.update_activity(f"EXPORTED {count} BEATS TO {path}")
        
        self.app.push_screen(PathPicker(), on_path_selected)

    def action_move_beat(self) -> None:
        ids = self._get_selected_ids()
        if not ids: 
            self.app.update_activity("ERROR: NO ASSETS SELECTED")
            return
        
        table = self.query_one("#library-table", DataTable)
        if hasattr(table, "selected_rows"): table.selected_rows.clear()

        def on_path_selected(path: str | None) -> None:
            if path:
                count = 0
                for beat_id in ids:
                    if self.app.library_engine.move_beat(beat_id, path):
                        count += 1
                if count > 0:
                    self.app.update_activity(f"MOVED {count} ASSETS")
                    self.refresh_library()
        
        self.app.push_screen(PathPicker(), on_path_selected)

    def action_preview(self) -> None:
        ids = self._get_selected_ids()
        if not ids:
            self.app.update_activity("ERROR: SELECT AN ASSET")
            return
        
        asset_id = ids[0]
        resolved = self.app.library_engine.resolve_asset_paths(asset_id)
        
        if not resolved:
            self.app.notify(f"Asset {asset_id} not found", severity="error")
            return

        # Get audio path from selector (it stores absolute paths)
        source_select = self.query_one("#audio-source-select", Select)
        audio_path = source_select.value if source_select.value and source_select.value != Select.BLANK else None

        if not audio_path:
            # Fallback to the first version if nothing selected
            versions = resolved.get("versions", [])
            if versions: audio_path = versions[0]["path"]

        if audio_path and os.path.exists(audio_path):
            self.app.audio_engine.play_preview(audio_path)
            self.currently_playing_id = asset_id
            
            # Find the display name for the activity log
            source_name = "Unknown Version"
            for v in resolved.get("versions", []):
                if v["path"] == audio_path:
                    source_name = v["name"].upper()
                    break
            
            self.app.update_activity(f"PLAYING [{source_name}]: {resolved.get('name', 'Unknown')}")
        else:
            self.app.notify(f"Audio file not found: {audio_path or 'N/A'}", severity="warning")

    def action_upload_yt(self) -> None:
        ids = self._get_selected_ids()
        if not ids: 
            self.app.update_activity("ERROR: SELECT AN ASSET")
            return
        
        asset_id = ids[0]
        # Switch to YouTube tab and apply templates
        try:
            self.app.query_one("#main-tabs").active = "pane-youtube"
            self.app.query_one(YoutubeTab).apply_templates(asset_id)
        except Exception as e:
            self.app.notify(f"Could not switch to YouTube tab: {str(e)}", severity="error")

    @work(exclusive=True)
    async def action_make_beat(self) -> None:
        ids = self._get_selected_ids()
        if not ids: 
            self.app.update_activity("ERROR: SELECT ASSETS FIRST")
            return

        table = self.query_one("#library-table", DataTable)
        if hasattr(table, "selected_rows"): table.selected_rows.clear()

        total = len(ids)
        count = 0
        self.app.update_activity(f"PROMOTING BEATS...", 0)

        for i, asset_id in enumerate(ids):
            try:
                self.app.library_engine.create_beat_from_audio(asset_id)
                count += 1
            except Exception as e:
                self.app.notify(f"Beat creation failed for {asset_id}: {str(e)}", severity="error")
                continue

            # Update progress
            progress = ((i + 1) / total) * 100
            self.app.update_activity(f"PROMOTING: {count}/{total}", progress)
            await asyncio.sleep(0.05) # Yield for UI update

        if count > 0:
            self.app.update_activity(f"FINISHED: CREATED {count} BEATS")
            self.refresh_library()
        else:
            self.app.update_activity("IDLE", 0)

    @work(exclusive=True)
    async def action_make_sample(self) -> None:
        ids = self._get_selected_ids()
        if not ids: 
            self.app.update_activity("ERROR: SELECT ASSETS FIRST")
            return

        table = self.query_one("#library-table", DataTable)
        if hasattr(table, "selected_rows"): table.selected_rows.clear()

        total = len(ids)
        count = 0
        self.app.update_activity(f"CREATING SAMPLES...", 0)

        for i, asset_id in enumerate(ids):
            try:
                self.app.library_engine.create_sample_from_audio(asset_id)
                count += 1
            except Exception as e:
                self.app.notify(f"Sample creation failed for {asset_id}: {str(e)}", severity="error")
                continue

            progress = ((i + 1) / total) * 100
            self.app.update_activity(f"SAMPLING: {count}/{total}", progress)
            await asyncio.sleep(0.05)

        if count > 0:
            self.app.update_activity(f"FINISHED: CREATED {count} SAMPLES")
            self.refresh_library()
        else:
            self.app.update_activity("IDLE", 0)
    @work(exclusive=True)
    async def action_make_song(self) -> None:
        ids = self._get_selected_ids()
        if not ids: 
            self.app.update_activity("ERROR: SELECT ASSETS FIRST")
            return

        table = self.query_one("#library-table", DataTable)
        if hasattr(table, "selected_rows"): table.selected_rows.clear()

        total = len(ids)
        count = 0
        self.app.update_activity(f"PROMOTING SONGS...", 0)

        for i, asset_id in enumerate(ids):
            try:
                self.app.library_engine.create_song_from_audio(asset_id)
                count += 1
            except Exception as e:
                self.app.notify(f"Song promotion failed for {asset_id}: {str(e)}", severity="error")
                continue

            progress = ((i + 1) / total) * 100
            self.app.update_activity(f"SONGS: {count}/{total}", progress)
            await asyncio.sleep(0.05)

        if count > 0:
            self.app.update_activity(f"FINISHED: PROMOTED {count} SONGS")
            self.refresh_library()
        else:
            self.app.update_activity("IDLE", 0)

    @work(exclusive=True, thread=True)
    async def action_separate_stems(self) -> None:
        ids = self._get_selected_ids()
        if not ids: 
            self.app.update_activity("ERROR: SELECT ASSETS FIRST")
            return

        table = self.query_one("#library-table", DataTable)
        if hasattr(table, "selected_rows"): table.selected_rows.clear()

        total = len(ids)
        count = 0
        self.app.update_activity(f"QUEUING STEMS...", 0)

        for i, asset_id in enumerate(ids):
            # We run this in a thread via @work(thread=True)
            # but run_stems itself is blocking.
            try:
                result = self.app.dispatcher.run_stems(asset_id)
                if result.success:
                    count += 1
                else:
                    self.app.notify(f"Stems failed for {asset_id}: {result.error_message}", severity="error")
            except Exception as e:
                self.app.notify(f"Stems initiation failed for {asset_id}: {str(e)}", severity="error")
                continue

            # After each asset, update overall batch progress
            progress = ((i + 1) / total) * 100
            self.app.update_activity(f"STEMS BATCH: {count}/{total}", progress)

        if count > 0:
            self.app.update_activity("IDLE")
            self.refresh_library()

    def action_downgrade_beat(self) -> None:
        ids = self._get_selected_ids()
        if not ids: 
            self.app.update_activity("ERROR: NO ASSETS SELECTED")
            return
        
        table = self.query_one("#library-table", DataTable)
        if hasattr(table, "selected_rows"): table.selected_rows.clear()
        
        count = 0
        for asset_id in ids:
            try:
                self.app.library_engine.downgrade_beat_to_raw(asset_id)
                count += 1
            except Exception as e:
                self.app.notify(f"Downgrade failed for {asset_id}: {str(e)}", severity="error")
                continue
        if count > 0:
            self.app.update_activity(f"FINISHED: DOWNGRADED {count} BEATS")
            self.refresh_library()

    def action_empty_trash(self) -> None:
        def on_confirm(confirmed: bool) -> None:
            if confirmed:
                count = self.app.library_engine.empty_trash()
                self.app.update_activity(f"TRASH EMPTIED: {count} ITEMS")
        self.app.push_screen(ConfirmModal("Are you sure? This will permanently delete all files in the trash."), on_confirm)

    def action_restore_trash(self) -> None:
        ids = self._get_selected_ids()
        if not ids: 
            self.app.update_activity("ERROR: SELECT A TARGET BEAT")
            return
        
        target_id = ids[0]
        asset = next((a for a in self.app.library_engine.get_assets() if str(a.get('id')) == target_id), None)
        if not asset or asset.get('asset_type') != AssetType.BEAT:
            self.app.update_activity("ERROR: TARGET MUST BE A BEAT")
            return
            
        trash_dir = self.app.library_engine.trash_dir
        if not os.path.exists(trash_dir):
            self.app.update_activity("TRASH IS EMPTY")
            return
            
        trash_items = [item for item in os.listdir(trash_dir) if os.path.isdir(os.path.join(trash_dir, item))]
        if not trash_items:
            self.app.update_activity("TRASH IS EMPTY")
            return
            
        def on_trash_selected(trash_name: str | None) -> None:
            if trash_name:
                try:
                    self.app.library_engine.restore_from_trash(trash_name, target_id)
                    self.app.update_activity(f"RESTORED: {asset['name']}")
                    self.refresh_library()
                except Exception as e:
                    self.app.notify(f"Restore failed: {str(e)}", severity="error")
                    self.refresh_library()
                    
        self.app.push_screen(TrashPicker(trash_items), on_trash_selected)

    def action_link_asset(self) -> None:
        ids = self._get_selected_ids()
        selected = [a for a in self.app.library_engine.get_assets() if str(a.get('id')) in ids]
        beats = [a for a in selected if a.get('asset_type') == 'beat']
        others = [a for a in selected if a.get('asset_type') != 'beat']
        
        if not beats or not others: 
            self.app.update_activity("ERROR: SELECT ONE BEAT AND OTHER ASSETS")
            return
            
        beat_id = beats[0]['id']
        linked_count = 0
        
        for other in others:
            role = "linked"
            if other.get('data_type') == 'image': role = "cover"
            elif other.get('asset_type') == 'raw': role = "source"
            
            # Update linked_assets dict
            beat_doc = next((a for a in self.app.library_engine.get_assets() if a['id'] == beat_id), None)
            if beat_doc:
                linked = beat_doc.get('linked_assets', {})
                linked[role] = other['id']
                updates = {'linked_assets': linked}
                if role == "cover": updates['cover_image_id'] = other['id'] # Keep legacy field in sync
                
                if self.app.library_engine.update_asset(beat_id, updates):
                    linked_count += 1
        
        if linked_count > 0:
            self.app.update_activity(f"LINKED {linked_count} ASSETS TO {beats[0]['name']}")
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
        if not ids: 
            self.app.update_activity("ERROR: NO ASSETS SELECTED")
            return
        table = self.query_one("#library-table", DataTable)
        if hasattr(table, "selected_rows"): table.selected_rows.clear()
        deleted_count = 0
        for asset_id in ids:
            if self.app.library_engine.delete_asset(asset_id): deleted_count += 1
        if deleted_count > 0:
            self.app.update_activity(f"REMOVED {deleted_count} ASSETS")
            self.refresh_library()

    def action_sync_library(self) -> None:
        self.app.update_activity("SYNCHRONIZING...")
        removed = self.app.library_engine.sync_library_with_disk()
        if removed > 0: self.app.notify(f"Cleaned {removed} missing files.", severity="warning")
        else: self.app.update_activity("LIBRARY SYNCHRONIZED")
        self.refresh_library()

    def action_select_all(self) -> None:
        table = self.query_one("#library-table", DataTable)
        if not hasattr(table, "selected_rows"): table.selected_rows = set()
        for row_key in table.rows: 
            asset_id = str(row_key.value).replace("row_", "")
            table.selected_rows.add(asset_id)
            table.update_cell(row_key, list(table.columns.keys())[0], "[*]")

    def action_deselect_all(self) -> None:
        table = self.query_one("#library-table", DataTable)
        if hasattr(table, "selected_rows"):
            table.selected_rows.clear()
            for row_key in table.rows:
                table.update_cell(row_key, list(table.columns.keys())[0], "[ ]")

    def action_clear_selection(self) -> None:
        """Clear all selected rows and hide inline editor if active."""
        inp = self.query_one("#inline-editor", Input)
        if not inp.has_class("hidden"):
            inp.add_class("hidden")
            self.query_one("#library-table", DataTable).focus()
            self.editing_asset_id = None
            return
            
        self.action_deselect_all()

    def action_focus_search(self) -> None:
        """Instantly focus the library search input."""
        self.query_one("#lib-filter-search", Input).focus()

    def action_invert_selection(self) -> None:
        """Invert the current selection of library rows."""
        table = self.query_one("#library-table", DataTable)
        if not hasattr(table, "selected_rows"):
            table.selected_rows = set()
        
        all_ids = {str(a.get('id')) for a in self.assets}
        new_selection = all_ids - table.selected_rows
        table.selected_rows = new_selection
        
        # Update markers
        for row_key in table.rows:
            asset_id = str(row_key.value).replace("row_", "")
            marker = "[*]" if asset_id in table.selected_rows else "[ ]"
            table.update_cell(row_key, list(table.columns.keys())[0], marker)
        
        self.app.update_activity("SELECTION INVERTED")

    def action_stop(self) -> None:
        self.app.audio_engine.stop_preview()
        self.currently_playing_id = None
        self.app.update_activity("PLAYBACK STOPPED")

class SafeDict(dict):
    """A dictionary that returns the key in curly braces if it's missing, for safe .format()"""
    def __missing__(self, key):
        return '{' + key + '}'

class YoutubeTab(Vertical):
    def compose(self) -> ComposeResult:
        with Horizontal(id="yt-row"):
            with Vertical(id="yt-left"):
                yield Label("UPLOAD HISTORY", classes="panel_title")
                yield DataTable(id="yt-uploads-table", cursor_type="row")
                yield Label("LIVE ON YOUTUBE", classes="panel_title")
                yield DataTable(id="yt-live-table", cursor_type="row")
                with Horizontal(id="yt-left-footer"):
                    yield Button("REFRESH", id="btn-yt-refresh")
                    yield Button("DELETE", id="btn-yt-delete", variant="error")

            with VerticalScroll(id="yt-right"):
                with TabbedContent(id="yt-right-tabs"):
                    with TabPane("PUBLISHING", id="pane-yt-pub"):
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

                        with Vertical(id="yt-desc-container", classes="yt-desc-container"):
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
                    
                    with TabPane("DEFAULTS", id="pane-yt-defaults"):
                        yield Label("YOUTUBE DEFAULTS & TEMPLATES", classes="panel_title")
                        
                        with Horizontal(classes="yt-form-row"):
                            yield Label("Title Tmpl", classes="menu-label")
                            yield Input(placeholder="{name} | {genre} Type Beat", id="yt-def-title")
                        
                        with Vertical(id="yt-def-desc-container", classes="yt-desc-container"):
                            yield Label("Desc Tmpl", classes="menu-label")
                            yield TextArea(id="yt-def-desc")
                        
                        with Horizontal(classes="yt-form-row"):
                            yield Label("Def Tags", classes="menu-label")
                            yield Input(placeholder="music, beat, hiphop...", id="yt-def-tags")
                        
                        yield Button("SAVE DEFAULTS", id="btn-yt-save-defaults", variant="success")

    def on_mount(self) -> None:
        table = self.query_one("#yt-uploads-table", DataTable)
        table.add_columns("ID", "TITLE", "STATUS", "DATE")
        
        live_table = self.query_one("#yt-live-table", DataTable)
        live_table.add_columns("TITLE", "VIDEO ID", "PUBLISHED")
        
        self._last_live_fetch = 0
        self.refresh_table()
        # self.fetch_live_videos()  # Removed to avoid intrusive auth on startup
        self.load_defaults()

    def load_defaults(self) -> None:
        defaults = self.app.library_engine.state_manager.get_yt_defaults()
        self.query_one("#yt-def-title", Input).value = defaults.get("title_template", "")
        self.query_one("#yt-def-desc", TextArea).text = defaults.get("desc_template", "")
        self.query_one("#yt-def-tags", Input).value = defaults.get("default_tags", "")

    @on(Button.Pressed, "#btn-yt-save-defaults")
    def handle_save_defaults(self) -> None:
        title = self.query_one("#yt-def-title", Input).value
        desc = self.query_one("#yt-def-desc", TextArea).text
        tags = self.query_one("#yt-def-tags", Input).value
        self.app.library_engine.state_manager.set_yt_defaults(title, desc, tags)
        self.app.update_activity("YOUTUBE DEFAULTS SAVED")


    @work(exclusive=True)
    async def fetch_live_videos(self, force: bool = False) -> None:
        """Fetch live videos from YouTube API with quota optimization."""
        now = time.time()
        # Only fetch once every 5 minutes unless forced
        if not force and (now - getattr(self, "_last_live_fetch", 0)) < 300:
            return

        self.app.update_activity("FETCHING YT VIDEOS...")
        try:
            yt_engine = self.app.dispatcher.youtube_engine
            # Use asyncio.to_thread for blocking call
            videos = await asyncio.to_thread(yt_engine.get_live_channel_videos)
            
            if videos:
                table = self.query_one("#yt-live-table", DataTable)
                table.clear()
                for v in videos:
                    table.add_row(
                        v.get('title', 'No Title'),
                        v.get('videoId', 'N/A'),
                        v.get('publishedAt', '')[:10]
                    )
                self._last_live_fetch = now
                self.app.update_activity("YT VIDEOS FETCHED")
            else:
                self.app.update_activity("NO YT VIDEOS FOUND")
        except Exception as e:
            self.app.notify(f"Error fetching live videos: {str(e)}", severity="error")
            self.app.update_activity("YT FETCH FAILED")

    def apply_templates(self, asset_id: str) -> None:
        """Apply metadata templates to the publishing fields."""
        try:
            # Fetch asset metadata
            asset = self.app.library_engine.get_asset(asset_id)
            if not asset: return
            
            meta = asset.get('metadata', {})
            metadata = {
                "name": asset.get("name", "N/A"),
                "bpm": asset.get("bpm", meta.get("bpm", "N/A")),
                "key": asset.get("key", meta.get("key", "N/A")),
                "genre": meta.get("genre", "N/A"),
                "mood": meta.get("mood", "N/A")
            }
            
            defaults = self.app.library_engine.state_manager.get_yt_defaults()
            safe_meta = SafeDict(metadata)
            
            self.query_one("#yt-title", Input).value = defaults.get("title_template", "").format_map(safe_meta)
            self.query_one("#yt-desc", TextArea).text = defaults.get("desc_template", "").format_map(safe_meta)
            self.query_one("#yt-tags", Input).value = defaults.get("default_tags", "")
            
            self.app.update_activity(f"TEMPLATES APPLIED: {metadata['name']}")
        except Exception as e:
            self.app.notify(f"Template Error: {str(e)}", severity="error")

    def refresh_table(self) -> None:
        try:
            table = self.query_one("#yt-uploads-table", DataTable)
            table.clear()
            uploads = self.app.library_engine.state_manager.get_yt_uploads()
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
        self.fetch_live_videos(force=True)

    @on(Button.Pressed, "#btn-yt-delete")
    @on(Button.Pressed, "#btn-yt-refresh")
    def handle_refresh(self) -> None:
        self.refresh_table()
        self.fetch_live_videos(force=True)

    @on(Button.Pressed, "#btn-yt-delete")
    def handle_delete(self) -> None:
        try:
            table = self.query_one("#yt-uploads-table", DataTable)
            if table.cursor_row is not None:
                row_keys = list(table.rows.keys())
                if table.cursor_row < len(row_keys):
                    upload_id = row_keys[table.cursor_row]
                    self.app.library_engine.state_manager.delete_yt_upload(upload_id)
                    self.refresh_table()
                    self.app.update_activity("UPLOAD ENTRY REMOVED")
        except: pass

class ActivityFooter(Horizontal):
    """A footer area for showing current background tasks and progress."""
    progress = reactive(0.0)
    status = reactive("IDLE")

    def compose(self) -> ComposeResult:
        yield Label("ACTIVITY:", id="activity-label")
        yield Label("IDLE", id="activity-status")
        yield Label("", id="activity-progress-text")

    def watch_progress(self, value: float) -> None:
        try:
            bar_width = 20
            filled = int((value / 100) * bar_width)
            bar = "█" * filled + "░" * (bar_width - filled)
            self.query_one("#activity-progress-text", Label).update(f"[{bar}] {value:3.0f}%")
        except: pass

    def watch_status(self, value: str) -> None:
        try:
            self.query_one("#activity-status", Label).update(value)
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
        
        # Initialize engines
        db_path = os.path.join(BASE_DIR, "state.db")
        self.library_engine = LibraryManagerEngine(db_path=db_path)
        self.audio_engine = AudioEngine()
        self.dispatcher = TaskDispatcher(BASE_DIR)
        self.dispatcher.app = self

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(id="main-tabs"):
            with TabPane("LIBRARY", id="pane-library"): yield LibraryTab()
            with TabPane("YOUTUBE", id="pane-youtube"): yield YoutubeTab()
        
        with Vertical(id="app-footer-container"):
            yield ActivityFooter(id="global-activity-footer")
            with Horizontal(id="footer-bar"):
                yield Button("IMPORT [Ctrl+I]", id="btn-toggle-import")
                yield Footer()

    def update_activity(self, status: str, progress: float = 0.0) -> None:
        """Update the global activity footer."""
        try:
            footer = self.query_one("#global-activity-footer", ActivityFooter)
            footer.status = status
            footer.progress = progress
        except: pass

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
        pass # Removed System Online notification

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
