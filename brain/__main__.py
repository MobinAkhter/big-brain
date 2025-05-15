# brain/__main__.py
import sys
import pathlib

# ─────────────────────────────────────────────
# Initialize Qt first
# ─────────────────────────────────────────────
from PySide6.QtWidgets import QApplication

# Create a single QApplication before any QWidget is built
_qt_app = QApplication(sys.argv)

# ─────────────────────────────────────────────
# Now import the rest
# ─────────────────────────────────────────────
import rumps
from brain.gui import AddNote, Ask, BrowseNotes

# ─────────────────────────────────────────────
# Locate icon
# ─────────────────────────────────────────────
ICO = pathlib.Path(__file__).resolve().parent.parent / "icons" / "brain.icns"
ICON = str(ICO) if ICO.exists() else None

# ─────────────────────────────────────────────
# Menubar app
# ─────────────────────────────────────────────
class SecondBrainApp(rumps.App):
    def __init__(self):
        super().__init__(
            name="Second Brain",
            icon=ICON,
            menu=[
                "New note",
                "Ask",
                "Browse notes",
                None,
                "Quit",
            ],
        )
        # Now it's safe to create Qt windows
        self.add_win    = AddNote(self)
        self.ask_win    = Ask()
        self.browse_win = BrowseNotes(self)

    @rumps.clicked("New note")
    def on_new(self, _):
        self.add_win.show()

    @rumps.clicked("Ask")
    def on_ask(self, _):
        self.ask_win.show()

    @rumps.clicked("Browse notes")
    def on_browse(self, _):
        self.browse_win.show()

    @rumps.clicked("Quit")
    def on_quit(self, _):
        rumps.quit_application()

# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────
if __name__ == "__main__":
    SecondBrainApp().run()
