import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.append(os.path.abspath('.openclaw/workspace/projects/beat-manager'))

from textual.app import App, ComposeResult
from tui import LibraryTab
from textual.widgets import DataTable, Input, Select

class TestApp(App):
    def compose(self) -> ComposeResult:
        yield LibraryTab()

class TestTUIMetadata(unittest.IsolatedAsyncioTestCase):
    @patch('tui.LibraryManagerEngine')
    async def test_metadata_inspector_and_actions(self, mock_engine_class):
        mock_engine = MagicMock()
        mock_engine_class.return_value = mock_engine
        
        beat_id = "test_beat_1"
        asset = {
            "id": beat_id,
            "name": "Test Beat",
            "asset_type": "beat",
            "data_type": "audio",
            "path": "/fake/path/TestBeat",
            "bpm": 120,
            "key": "C min",
            "metadata": {
                "genre": "Hip Hop",
                "mood": "Dark"
            }
        }
        mock_engine.get_assets.return_value = [asset]
        mock_engine.generate_mp3_for_beat.return_value = True
        
        app = TestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            
            tab = app.query_one(LibraryTab)
            table = app.query_one("#library-table", DataTable)
            
            self.assertEqual(len(table.rows), 1)
            
            # Select the first row explicitly
            tab.populate_inspector(beat_id) # Using populate directly to avoid keyboard events sync issues
            
            await pilot.pause()
            
            inspector = app.query_one("#library-inspector")
            self.assertFalse(inspector.has_class("hidden"))
            
            genre_input = app.query_one("#meta-genre", Input)
            self.assertEqual(genre_input.value, "Hip Hop")
            
            mood_input = app.query_one("#meta-mood", Input)
            self.assertEqual(mood_input.value, "Dark")
            
            bpm_input = app.query_one("#meta-bpm", Input)
            self.assertEqual(bpm_input.value, "120")
            
            # Modify and Save
            genre_input.value = "Trap"
            from textual.widgets import Button
            app.query_one("#btn-inspector-save", Button).press()
            await pilot.pause()
            
            print(f"Notifications: {[n.message for n in app._notifications]}")
            
            mock_engine.update_asset.assert_called()
            call_args = mock_engine.update_asset.call_args
            self.assertEqual(call_args[0][0], beat_id)
            self.assertEqual(call_args[0][1]['metadata']['genre'], "Trap")
            
            # Trigger actions
            table.selected_rows = {beat_id}
            
            dropdown = app.query_one("#lib-edit-dropdown", Select)
            dropdown.value = "convert_mp3"
            await pilot.pause()
            
            mock_engine.generate_mp3_for_beat.assert_called_once_with(beat_id)

if __name__ == "__main__":
    unittest.main()
