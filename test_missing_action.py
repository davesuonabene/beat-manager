from textual.app import App
from textual.binding import Binding

class MissingActionApp(App):
    BINDINGS = [Binding("r", "rename_asset", "Rename")]

if __name__ == "__main__":
    MissingActionApp().run()
