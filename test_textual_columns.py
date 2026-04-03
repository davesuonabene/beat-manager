from textual.app import App, ComposeResult
from textual.widgets import DataTable

class TableApp(App):
    def compose(self) -> ComposeResult:
        table = DataTable()
        table.add_columns("A", "B")
        yield table

    def on_mount(self):
        table = self.query_one(DataTable)
        try:
            print("Columns keys:", list(table.columns.keys()))
            col_key = list(table.columns.keys())[0]
            print("First column key:", col_key)
            print("Using index 0:", table.columns[0])
        except Exception as e:
            print("Error accessing index 0:", type(e), str(e))
        self.exit()

if __name__ == "__main__":
    TableApp().run()
