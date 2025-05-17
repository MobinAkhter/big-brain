import sys
from PySide6.QtWidgets import QApplication
_qt_app = QApplication(sys.argv)
import rumps
import pathlib
from brain.gui import AddNote, Ask, BrowseNotes

ICO = pathlib.Path(__file__).resolve().parent.parent / "icons" / "brain.icns"
ICON = str(ICO) if ICO.exists() else None

class SecondBrainApp(rumps.App):
    def __init__(self):
        super().__init__("Second Brain", icon=ICON, menu=["New note", "Ask", "Browse notes", "Quit"])
        self.add_win = AddNote(self)
        self.ask_win = Ask()
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

if __name__ == "__main__":
    SecondBrainApp().run()