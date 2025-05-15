# brain/__main__.py
import sys, pathlib, threading
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QAction, QCursor
from .gui import AddNote, Ask

# ─────────────────────────────────────────────
# Qt application and tray
# ─────────────────────────────────────────────
app = QApplication(sys.argv)

icon_path = pathlib.Path(__file__).resolve().parent.parent / "icons" / "brain.icns"
icon = (
    QIcon(str(icon_path))
    if icon_path.exists()
    else app.style().standardIcon(app.style().SP_MessageBoxInformation)
)

tray = QSystemTrayIcon(icon)
menu = QMenu()

add_win = AddNote(tray)   # need tray for toast messages
ask_win = Ask()

menu.addAction(QAction("New note", triggered=add_win.show))
menu.addAction(QAction("Ask", triggered=ask_win.show))
menu.addSeparator()
menu.addAction(QAction("Quit", triggered=app.quit))

tray.setContextMenu(menu)
tray.setToolTip("Second Brain")

def on_tray_activated(reason):
    if reason == QSystemTrayIcon.Trigger:      # left‑click
        add_win.show()
    elif reason == QSystemTrayIcon.Context:    # right‑click
        menu.exec(QCursor.pos())

tray.activated.connect(on_tray_activated)

# ─────────────────────────────────────────────
# Custom global‑shortcut listener (pynput, caps‑lock‑safe)
# ─────────────────────────────────────────────
def start_hotkeys():
    try:
        from pynput import keyboard
    except ImportError:
        tray.showMessage(
            "Second Brain",
            "Global shortcuts disabled – install the 'pynput' package",
            QSystemTrayIcon.Warning,
            6000,
        )
        return

    # Map combos to actions
    hotkeys = {
        frozenset([keyboard.Key.cmd, keyboard.Key.shift, keyboard.KeyCode.from_char("n")]): add_win.show,
        frozenset([keyboard.Key.cmd, keyboard.Key.shift, keyboard.KeyCode.from_char("f")]): ask_win.show,
    }

    pressed = set()

    def on_press(key):
        # Ignore Caps Lock entirely to avoid the macOS bug
        if key == keyboard.Key.caps_lock:
            return
        pressed.add(key)
        for combo, action in hotkeys.items():
            if combo <= pressed:
                action()

    def on_release(key):
        if key == keyboard.Key.caps_lock:
            return
        pressed.discard(key)

    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.daemon = True   # exit cleanly with the app
    listener.start()

threading.Thread(target=start_hotkeys, daemon=True).start()

# ─────────────────────────────────────────────
tray.show()
sys.exit(app.exec())
