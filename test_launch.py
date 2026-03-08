from textual.app import App, ComposeResult
from textual.widgets import DirectoryTree, Checkbox
import os

class TestApp(App):
    def compose(self) -> ComposeResult:
        yield DirectoryTree(os.path.expanduser("~"))
        yield Checkbox("Test")

if __name__ == "__main__":
    app = TestApp()
    print("OK - Initialized")
