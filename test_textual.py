from textual.app import App, ComposeResult
from textual.widgets import DataTable
import traceback

class TestApp(App):
    def compose(self) -> ComposeResult:
        t = DataTable()
        t.add_columns("A", "B")
        yield t
    
    def on_mount(self):
        t = self.query_one(DataTable)
        with open("test_output.txt", "w") as f:
            f.write(f"type: {type(t.columns)}\n")
            try:
                col0 = t.columns[0]
                f.write(f"Success[0]: {col0}\n")
            except Exception as e:
                f.write(f"Error[0]: {type(e)} - {e}\n")
            try:
                keys = list(t.columns.keys())
                f.write(f"Keys: {keys}\n")
            except Exception as e:
                f.write(f"Error keys: {type(e)} - {e}\n")
            try:
                f.write(f"Is cursor_row supported? {hasattr(t, 'cursor_row')}\n")
                f.write(f"Is action_cursor_down supported? {hasattr(t, 'action_cursor_down')}\n")
            except Exception as e:
                pass
        self.exit()

if __name__ == "__main__":
    TestApp().run()
