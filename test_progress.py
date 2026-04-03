from textual.app import App, ComposeResult
from textual.widgets import ProgressBar, Label
from textual.containers import Horizontal
from textual import events, on

class TestApp(App):
    CSS = """
    Horizontal {
        height: 3;
        background: blue;
    }
    ProgressBar {
        width: 1fr;
        background: red;
    }
    """
    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Label("START")
            yield ProgressBar(id="p", show_eta=False, show_percentage=False)
            yield Label("END")
        yield Label("Click info:", id="info")

    def on_mount(self):
        p = self.query_one(ProgressBar)
        p.total = 100
        p.progress = 50

    @on(events.Click, "#p")
    def handle_click(self, event: events.Click):
        p = self.query_one(ProgressBar)
        self.query_one("#info", Label).update(
            f"x={event.x}, offset_x={event.offset_x}, width={p.size.width}, content_width={p.content_size.width}"
        )

if __name__ == "__main__":
    TestApp().run()
