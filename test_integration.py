import os
import sys
import unittest
import shutil
from unittest.mock import MagicMock, patch

sys.path.append(os.path.abspath('.openclaw/workspace/projects/beat-manager'))

from textual.app import App, ComposeResult
from tui import LibraryTab, CollectionManagerModal
from textual.widgets import Select, Input, Button, DataTable
from app.models.schemas import CollectionType, AssetType

class TestApp(App):
    def compose(self) -> ComposeResult:
        yield LibraryTab()

class TestLibraryIntegration(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.test_dir = "test_integration_env"
        os.makedirs(self.test_dir, exist_ok=True)
        self.db_path = os.path.join(self.test_dir, "test_state.json")
        
    def tearDown(self):
        shutil.rmtree(self.test_dir)

    @patch('tui.LibraryManagerEngine')
    async def test_full_collection_workflow(self, mock_engine_class):
        mock_engine = MagicMock()
        mock_engine_class.return_value = mock_engine
        
        # 1. Setup mock assets
        sample_id = "sample1"
        assets = [
            {
                "id": sample_id,
                "name": "Heavy Snare",
                "asset_type": "sample",
                "data_type": "audio",
                "path": "/fake/path/snare.wav",
                "collection_id": None
            }
        ]
        mock_engine.get_assets.return_value = assets
        mock_engine.state_manager.get_collections.return_value = []
        mock_engine.state_manager.get_collections_by_type.return_value = []
        
        app = TestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            
            # Switch to SAMPLES filter
            type_select = app.query_one("#lib-filter-type", Select)
            type_select.value = "sample"
            await pilot.pause()
            
            # Verify sample is in table
            table = app.query_one("#library-table", DataTable)
            while len(table.rows) == 0:
                await pilot.pause()
            assert len(table.rows) == 1
            
            # 2. Open Collection Modal
            # Select the row
            table.move_cursor(row=0)
            await pilot.press("g") # Shortcut for manage_collection
            await pilot.pause()
            
            # Wait for modal
            while not any(isinstance(s, CollectionManagerModal) for s in app.screen_stack):
                await pilot.pause()
            
            modal = next(s for s in app.screen_stack if isinstance(s, CollectionManagerModal))
            
            # 3. Create a collection in the modal
            col_name = "Pack Vol 1"
            col_id = "new_col_123"
            
            def mock_add_col(data):
                # Simulate collection being added
                mock_engine.state_manager.get_collections.return_value = [
                    {"id": col_id, "name": col_name, "type": "sample"}
                ]
                mock_engine.state_manager.get_collections_by_type.return_value = [
                    {"id": col_id, "name": col_name, "type": "sample"}
                ]
                return True
            
            mock_engine.state_manager.add_collection.side_effect = mock_add_col
            
            input_field = modal.query_one("#col-new-name", Input)
            input_field.value = col_name
            await pilot.click("#btn-col-create")
            await pilot.pause()
            
            # 4. Assign and Close
            mock_engine.assign_to_collection.return_value = True
            # Update asset list to show assigned collection
            assets[0]['collection_id'] = col_id
            
            await pilot.click("#btn-col-assign")
            await pilot.pause()
            
            # 5. Verify E2E Loop
            mock_engine.assign_to_collection.assert_called_with(sample_id, col_id, "sample")
            
            # Check if Collection filter was updated in main UI
            col_filter = app.query_one("#lib-filter-collection", Select)
            # options is internal _options
            option_labels = [opt[0] for opt in col_filter._options]
            assert col_name in option_labels

if __name__ == "__main__":
    unittest.main()
