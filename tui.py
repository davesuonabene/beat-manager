import os
import glob
import json
import time
import math
import random
from datetime import datetime
from typing import List, Tuple, Dict, Any

from textual.app import App, ComposeResult, RenderResult
from textual.widgets import (
    Header, Footer, Static, Input, Button, DataTable, 
    Label, TabbedContent, TabPane, Select, ListView,
    ListItem, TextArea, LoadingIndicator, ProgressBar,
    Digits, Checkbox, DirectoryTree, Sparkline
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

class Island(Container):
    """A professional panel container."""
    pass

class ImportOverlay(Vertical):
    """A professional overlay for scanning and importing assets."""
    BINDINGS = [
        Binding("space", "toggle_selection", "Select"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.found_assets = []

    def compose(self) -> ComposeResult:
        with Horizontal(id="import-toolbar"):
            yield Label("IMPORT ASSETS", id="import-title")
            yield Input(placeholder="Source directory path...", id="import-search-path")
            yield Button("BROWSE", id="btn-import-browse")
            yield Button("SCAN", id="btn-import-scan", variant="primary")
            yield Checkbox("MOVE", id="import-delete-source", value=False)
            yield Checkbox("SKIP DUPES", id="import-skip-dupes", value=True)

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
            row_key = row_keys[table.cursor_row]
            if not hasattr(table, "selected_rows"): table.selected_rows = set()

            if row_key in table.selected_rows:
                table.selected_rows.remove(row_key)
                table.update_cell(row_key, list(table.columns.keys())[0], "[ ]")
            else:
                table.selected_rows.add(row_key)
                table.update_cell(row_key, list(table.columns.keys())[0], "[*]")
            table.action_cursor_down()

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
        self.add_class("hidden")
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
            for asset in self.found_assets:
                table.add_row(
                    "[ ]",
                    asset['name'],
                    asset['type'].upper(),
                    os.path.basename(asset['path']),
                    asset.get('status', 'Ready'),
                    key=asset['path']
                )
            self.app.notify(f"Scanned {len(self.found_assets)} items.")
        except Exception as e:
            self.app.notify(f"Scan failed: {str(e)}", severity="error")

    @on(Button.Pressed, "#btn-import-collect")
    def handle_collect(self) -> None:
        try:
            table = self.query_one("#import-results-table", DataTable)
            selected_indices = []
            selected_rows = getattr(table, "selected_rows", set())
            if selected_rows:
                row_keys = list(table.rows.keys())
                for key in selected_rows:
                    try:
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
        with Container(id="picker-container"):
            yield Label("FILE SYSTEM BROWSER", classes="section-label")
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

class SeekableBar(Static):
    """A custom progress bar using theme-aware styling."""
    progress = reactive(0.0)
    total = reactive(1.0)

    def render(self) -> RenderResult:
        from rich.progress_bar import ProgressBar as RichProgressBar
        return RichProgressBar(
            total=self.total, 
            completed=self.progress, 
            width=None, 
            pulse=False,
            style="#262626",
            complete_style="#3b82f6",
            finished_style="#3b82f6"
        )

    def on_click(self, event: events.Click) -> None:
        if self.total > 0:
            percentage = event.x / self.size.width
            self.post_message(self.SeekRequested(percentage))

    class SeekRequested(Message):
        def __init__(self, percentage: float) -> None:
            self.percentage = percentage
            super().__init__()

class WaveformDisplay(Static):
    """A responsive waveform display that uses Sparklines to mock an audio trace."""
    class SeekRequested(Message):
        def __init__(self, percentage: float) -> None:
            self.percentage = percentage
            super().__init__()

    def compose(self) -> ComposeResult:
        data = [abs(math.sin(i / 5.0)) * 10 + random.random() * 5 for i in range(100)]
        yield Sparkline(data, summary_function=max)
        
    def on_click(self, event: events.Click) -> None:
        percentage = event.x / self.size.width
        self.post_message(self.SeekRequested(percentage))

    def update_data(self, data: List[float]) -> None:
        self.query_one(Sparkline).data = data

class Player(Horizontal):
    """Professional audio transport controls."""
    def compose(self) -> ComposeResult:
        yield Button("PLAY", id="btn-player-play", variant="success")
        yield Button("STOP", id="btn-player-stop", variant="error")
        yield Label("00:00", id="audio-time-current")
        yield SeekableBar(id="audio-progress")
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
            bar = self.query_one("#audio-progress", SeekableBar)
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

    def on_seekable_bar_seek_requested(self, message: SeekableBar.SeekRequested) -> None:
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

class LibraryTab(Container):
    currently_playing_id = reactive(None)

    BINDINGS = [
        Binding("p", "preview", "Preview"),
        Binding("s", "stop", "Stop"),
        Binding("b", "make_beat", "Make Beat"),
        Binding("e", "export_beat", "Export"),
        Binding("m", "move_beat", "Move"),
        Binding("f2", "rename_asset", "Rename"),
        Binding("delete", "delete_asset", "Delete"),
        Binding("ctrl+a", "select_all", "Select All"),
        Binding("f5", "sync_library", "Sync"),
        Binding("c", "set_cover", "Set Cover"),
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
            with Horizontal(id="lib-header-row-1"):
                yield Input(placeholder="Search assets...", id="lib-filter-search")
                yield Select([
                    ("ALL TYPES", "all"),
                    ("RAW AUDIO", "raw"),
                    ("BEATS", "beat"),
                    ("IMAGES", "cover")
                ], id="lib-filter-type", value="all")
            
            with Horizontal(id="lib-header-row-2"):
                yield Select([
                    ("ACTIONS...", "none"),
                    ("PREVIEW [P]", "preview"),
                    ("MAKE BEAT [B]", "make_beat"),
                    ("DOWNGRADE [D]", "downgrade"),
                    ("SET COVER [C]", "set_cover"),
                    ("EXPORT [E]", "export"),
                    ("MOVE [M]", "move"),
                    ("DISK SYNC [F5]", "sync"),
                    ("IMPORT [^I]", "import"),
                    ("DELETE [DEL]", "delete")
                ], id="lib-actions-dropdown", value="none")
        
        with Vertical(id="library-main-content"):
            with Horizontal(id="library-body-split"):
                with Container(id="library-table-container"):
                    yield DataTable(id="library-table", cursor_type="row")
                    yield Input(id="inline-editor", classes="hidden")
                
                with Vertical(id="library-inspector", classes="island hidden"):
                    yield Label("WAVEFORM INSPECTOR", classes="section-label")
                    yield WaveformDisplay(id="inspector-waveform")
            yield Player(id="library-player")

    def on_mount(self) -> None:
        table = self.query_one("#library-table", DataTable)
        table.selected_rows = set()
        table.add_columns(" ", "ID", "NAME", "TYPE", "DATA", "BPM", "KEY", "DURATION")
        self.library_engine = LibraryManagerEngine()
        self.refresh_library()

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
            inspector = self.query_one("#library-inspector")
            waveform = self.query_one("#inspector-waveform", WaveformDisplay)
            if value is not None:
                inspector.remove_class("hidden")
                # Generate new dummy waveform for visual variety
                new_data = [abs(math.sin(i / random.uniform(3.0, 8.0))) * 10 + random.random() * 5 for i in range(100)]
                waveform.update_data(new_data)
            else:
                inspector.add_class("hidden")
        except: pass
        self.refresh_library()

    def refresh_library(self, search: str | None = None, type_filter: str | None = None) -> None:
        try:
            table = self.query_one("#library-table", DataTable)
            if search is None:
                search = self.query_one("#lib-filter-search", Input).value
                type_filter = str(self.query_one("#lib-filter-type", Select).value)
            
            all_assets = self.library_engine.get_assets()
            self.assets = [a for a in all_assets if (type_filter == "all" or a.get('asset_type', a.get('type', 'raw')) == type_filter) and (not search or search.lower() in a.get('name', '').lower())]
            
            # Save cursor state
            old_cursor_row = table.cursor_row
            
            table.clear()
            selected_rows = getattr(table, "selected_rows", set())
            for a in self.assets:
                asset_id = str(a.get('id'))
                marker = "[*]" if asset_id in selected_rows else "[ ]"
                
                raw_name = a.get('name', 'Unknown')
                display_name = f"[bold green]▶ {raw_name}[/bold green]" if asset_id == self.currently_playing_id else raw_name
                
                table.add_row(
                    marker,
                    asset_id,
                    display_name,
                    a.get('asset_type', 'N/A').upper(),
                    a.get('data_type', 'AUDIO').upper(),
                    str(a.get('bpm', '') or ""),
                    str(a.get('key', '') or ""),
                    f"{a.get('duration', 0):.1f}s" if a.get('duration') else "N/A",
                    key=asset_id
                )
                
            # Restore cursor state
            playing_index = None
            if self.currently_playing_id:
                for i, a in enumerate(self.assets):
                    if str(a.get('id')) == self.currently_playing_id:
                        playing_index = i
                        break
            
            if playing_index is not None:
                table.cursor_row = playing_index
            elif old_cursor_row is not None and len(self.assets) > 0:
                table.cursor_row = min(old_cursor_row, len(self.assets) - 1)
        except: pass

    @on(Input.Changed, "#lib-filter-search")
    @on(Select.Changed, "#lib-filter-type")
    def handle_filters_changed(self) -> None:
        self.refresh_library()

    @on(Select.Changed, "#lib-actions-dropdown")
    def handle_action_selected(self, event: Select.Changed) -> None:
        action = str(event.value)
        if action == "none": return
        
        # Reset dropdown
        self.query_one("#lib-actions-dropdown", Select).value = "none"

        if action == "preview": self.action_preview()
        elif action == "make_beat": self.action_make_beat()
        elif action == "downgrade": self.action_downgrade_beat()
        elif action == "set_cover": self.action_set_cover()
        elif action == "export": self.action_export_beat()
        elif action == "move": self.action_move_beat()
        elif action == "sync": self.action_sync_library()
        elif action == "import": self.app.action_toggle_import()
        elif action == "delete": self.action_delete_asset()

    def on_waveform_display_seek_requested(self, message: WaveformDisplay.SeekRequested) -> None:
        try:
            player = self.app.audio_engine.player
            if player.duration > 0 and player.is_playing:
                target = message.percentage * player.duration
                player.play(player.current_file, start_offset=target)
        except: pass

    def action_toggle_selection(self) -> None:
        table = self.query_one("#library-table", DataTable)
        if table.cursor_row is not None:
            row_keys = list(table.rows.keys())
            row_key = row_keys[table.cursor_row]
            if not hasattr(table, "selected_rows"): table.selected_rows = set()

            if row_key in table.selected_rows:
                table.selected_rows.remove(row_key)
                table.update_cell(row_key, list(table.columns.keys())[0], "[ ]")
            else:
                table.selected_rows.add(row_key)
                table.update_cell(row_key, list(table.columns.keys())[0], "[*]")
            table.action_cursor_down()

    def _get_selected_ids(self) -> List[str]:
        try:
            table = self.query_one("#library-table", DataTable)
            selected_rows = getattr(table, "selected_rows", set())
            if selected_rows:
                return [str(table.get_row(key)[1]) for key in selected_rows]
            if table.cursor_row is not None:
                row_keys = list(table.rows.keys())
                if 0 <= table.cursor_row < len(row_keys):
                    return [str(table.get_row(row_keys[table.cursor_row])[1])]
        except: pass
        return []

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
        count = 0
        for asset_id in ids:
            try:
                self.library_engine.create_beat_from_audio(asset_id)
                count += 1
            except: continue
        if count > 0:
            self.app.notify(f"Created {count} beat structures.")
            self.refresh_library()

    def action_downgrade_beat(self) -> None:
        ids = self._get_selected_ids()
        if not ids: return self.app.notify("No assets selected", severity="warning")
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

    def action_set_cover(self) -> None:
        ids = self._get_selected_ids()
        selected = [a for a in self.library_engine.get_assets() if str(a.get('id')) in ids]
        beats = [a for a in selected if a.get('asset_type') == 'beat']
        images = [a for a in selected if a.get('data_type') == 'image']
        if not beats or not images: return self.app.notify("Select one BEAT and one IMAGE.", severity="warning")
        try:
            self.library_engine.set_beat_cover(beats[0]['id'], images[0]['id'])
            self.app.notify(f"Cover linked to {beats[0]['name']}")
            self.refresh_library()
        except Exception as e: self.app.notify(f"Linking failed: {str(e)}", severity="error")

    def action_rename_asset(self) -> None:
        try:
            table = self.query_one("#library-table", DataTable)
            if table.cursor_row is not None:
                row_keys = list(table.rows.keys())
                if table.cursor_row >= len(row_keys): return
                row_key = row_keys[table.cursor_row]
                row_data = table.get_row(row_key)
                asset_id = str(row_data[1])
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
        if hasattr(table, "selected_rows"): table.selected_rows = set()
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
            table.selected_rows.add(row_key)
            table.update_cell(row_key, list(table.columns.keys())[0], "[*]")
        self.app.notify("All items selected.")

    def action_stop(self) -> None:
        self.app.audio_engine.stop_preview()
        self.currently_playing_id = None
        self.app.notify("Playback stopped.")

class YoutubeTab(Container):
    def compose(self) -> ComposeResult:
        with Horizontal(id="yt-row"):
            with VerticalScroll(id="yt-left", classes="island"):
                yield Label("UPLOAD HISTORY", classes="section-label")
                yield DataTable(id="yt-uploads-table", cursor_type="row")
                with Horizontal(classes="multi-input-row"):
                    yield Button("REFRESH", id="btn-yt-refresh", variant="default")
                    yield Button("DELETE", id="btn-yt-delete", variant="error")
            
            with VerticalScroll(id="yt-right", classes="island"):
                yield Label("YOUTUBE PUBLISHING", classes="section-label")
                
                with Vertical(classes="form-group"):
                    yield Label("Video File Path")
                    yield Input(placeholder="/path/to/video.mp4", id="yt-video", value=os.path.join(BASE_DIR, "output.mp4"))
                
                with Vertical(classes="form-group"):
                    yield Label("Thumbnail Path (Optional)")
                    yield Input(placeholder="/path/to/thumb.jpg", id="yt-thumb")
                
                with Vertical(classes="form-group"):
                    yield Label("Video Title")
                    yield Input(placeholder="Enter title...", id="yt-title")
                
                with Vertical(classes="form-group"):
                    yield Label("Description")
                    yield TextArea(id="yt-desc", classes="small-text-area")
                
                with Vertical(classes="form-group"):
                    yield Label("Tags (Comma Separated)")
                    yield Input(placeholder="music, beat, hiphop...", id="yt-tags")
                
                with Horizontal(classes="multi-input-row"):
                    yield Select([("Music", "10"), ("Entertainment", "24")], id="yt-cat", value="10")
                    yield Select([("Private", "private"), ("Unlisted", "unlisted"), ("Public", "public")], id="yt-privacy", value="private")
                
                with Vertical(classes="form-group"):
                    yield Label("Schedule (Optional ISO 8601)")
                    yield Input(placeholder="2024-01-01T12:00:00Z", id="yt-schedule")
                
                with Horizontal(classes="multi-input-row"):
                    yield Button("SAVE DRAFT", id="btn-yt-save-draft", variant="default")
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

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            with TabPane("LIBRARY"): yield LibraryTab()
            with TabPane("YOUTUBE"): yield YoutubeTab()
        yield ImportOverlay(id="import-overlay", classes="hidden")
        with Horizontal(id="footer-bar"):
            yield Button("IMPORT [Ctrl+I]", id="btn-toggle-import")
            yield Footer()

    def action_toggle_import(self) -> None: self.show_import = not self.show_import
    def watch_show_import(self, show: bool) -> None: self.query_one("#import-overlay").set_class(not show, "hidden")
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
