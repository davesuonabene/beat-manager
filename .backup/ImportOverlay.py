class ImportOverlay(Vertical):
    """A slide-up overlay for scanning and importing assets."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.found_assets = []

    def compose(self) -> ComposeResult:
        with Horizontal(id="import-toolbar"):
            yield Label("IMPORT", id="import-title")
            yield Input(placeholder="Scan path...", id="import-search-path")
            yield Button("DIR", id="btn-import-browse")
            yield Button("🔄", id="btn-import-scan", variant="primary")
            yield Checkbox("DEL", id="import-delete-source", value=False)
            yield Checkbox("SKIP", id="import-skip-dupes", value=True)

        yield DataTable(id="import-results-table", cursor_type="row")
        
        with Horizontal(id="import-footer"):
            yield Static(id="import-footer-spacer")
            yield Button("PLAY", id="btn-import-preview", variant="warning")
            yield Button("ADD ALL", id="btn-import-all", variant="success")
            yield Button("ADD SELECTED", id="btn-import-collect", variant="primary")
            yield Button("CLOSE", id="btn-import-close", variant="error")

    def on_mount(self) -> None:
        table = self.query_one("#import-results-table", DataTable)
        table.selected_rows = set()
        table.add_columns("NAME", "TYPE", "PATH", "STATUS")

    @on(DataTable.RowSelected, "#import-results-table")
    def handle_row_selected_import(self, event: DataTable.RowSelected) -> None:
        table = event.data_table
        if not hasattr(table, "selected_rows"):
            table.selected_rows = set()

        if event.row_key in table.selected_rows:
            table.selected_rows.remove(event.row_key)
            self.app.notify("Deselected.")
        else:
            table.selected_rows.add(event.row_key)
            self.app.notify("Selected.")

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
                self.app.notify("Please select a valid directory", severity="error")
                return
            
            if os.path.isfile(path):
                path = os.path.dirname(path)

            self.found_assets = self.app.library_engine.scan_for_import(path)
            table = self.query_one("#import-results-table", DataTable)
            table.clear()
            if not hasattr(table, "selected_rows"):
                table.selected_rows = set()
            table.selected_rows.clear()
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
                self.app.notify("No assets selected", severity="warning")
                return

            delete_after = self.query_one("#import-delete-source", Checkbox).value
            skip_dupes = self.query_one("#import-skip-dupes", Checkbox).value
            
            count = 0
            for idx in selected_indices:
                if 0 <= idx < len(self.found_assets):
                    asset_data = self.found_assets[idx]
                    
                    if skip_dupes and asset_data.get('status') == 'Exists':
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
            
            self.app.notify(f"Added {count} assets to library.")
            self.handle_scan() 
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