from textual.app import App, ComposeResult
from textual.widgets import DataTable, Input
from textual.coordinate import Coordinate
from textual import on, work
import traceback

class TestApp(App):
    def compose(self) -> ComposeResult:
        t = DataTable()
        t.add_columns("A", "B", "C")
        t.add_row("1", "2", "3")
        yield t
        i = Input(id="inline-editor")
        yield i
        
    @work
    async def run_action(self):
        import asyncio
        await asyncio.sleep(0.5)
        try:
            t = self.query_one(DataTable)
            if t.cursor_row is not None:
                class DummyEvent:
                    def __init__(self, r, c): self.coordinate = Coordinate(r, c)
                
                # Try getting the region exactly as handle_cell_selected does
                e = DummyEvent(t.cursor_row, 2)
                region = t._get_cell_region(e.coordinate)
                with open("test_out.txt", "w") as f:
                    f.write(f"Coord match! Region: {region}\n")
        except Exception as e:
            with open("test_out.txt", "w") as f:
                f.write(f"Error: {type(e)} {e}\n")
                f.write(traceback.format_exc())
        self.exit()

    def on_mount(self):
        self.run_action()

if __name__ == "__main__":
    TestApp().run()
