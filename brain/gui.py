# brain/gui.py
from PySide6.QtWidgets import (
    QWidget,
    QTextEdit,
    QVBoxLayout,
    QLineEdit,
    QPushButton,
    QHBoxLayout,
    QSystemTrayIcon,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QKeySequence

from .storage import add, topk
from .llm import embed, chat


# ─────────────────────────────────────────────
# Custom QTextEdit for note input with key handling
# ─────────────────────────────────────────────
class NoteTextEdit(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Save):          # Cmd+S
            self.parent._save_note()
        elif event.key() == Qt.Key_Escape:            # Esc
            self.parent.close()
        else:
            super().keyPressEvent(event)


# ─────────────────────────────────────────────
# “New note” window
# ─────────────────────────────────────────────
class AddNote(QWidget):
    def __init__(self, tray):
        super().__init__()
        self.tray = tray
        self.setWindowTitle("Add note")
        self.setFixedSize(QSize(480, 300))

        self.text = NoteTextEdit(self)
        self.text.setPlaceholderText("Paste or type any snippet…")

        # Buttons
        save_btn = QPushButton("Save (⌘S)")
        cancel_btn = QPushButton("Close")

        save_btn.clicked.connect(self._save_note)
        cancel_btn.clicked.connect(self.close)

        # Layout
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self.text)
        layout.addLayout(btn_row)

    # -------- save / toast --------
    def _save_note(self):
        body = self.text.toPlainText().strip()
        if not body:
            return

        vec = embed(body)
        add(body, vec)

        self.tray.showMessage(
            "Second Brain",
            "Note saved ✔",
            QSystemTrayIcon.Information,
            2000,
        )
        self.text.clear()          # keep window open, ready for next note
        self.text.setFocus()

    # Make sure text box is focused every time window shows
    def show(self):
        super().show()
        self.text.setFocus()


# ─────────────────────────────────────────────
# “Ask” window
# ─────────────────────────────────────────────
class Ask(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ask")
        self.setFixedSize(QSize(520, 360))

        self.query = QLineEdit()
        self.query.setPlaceholderText("Type your question and press ⏎")

        self.answer = QTextEdit(readOnly=True)

        layout = QVBoxLayout(self)
        layout.addWidget(self.query)
        layout.addWidget(self.answer)

        self.query.returnPressed.connect(self._ask)

    # -------- run query --------
    def _ask(self):
        q = self.query.text().strip()
        self.query.clear()
        if not q:
            return

        q_vec = embed(q)
        context = topk(q_vec, k=4)

        prompt = (
            "Answer using ONLY the context below. Cite note numbers in [brackets].\n\n"
            + "\n\n".join(f"[{i}] {b}" for i, b in context)
            + f"\n\nQ: {q}\nA:"
        )

        self.answer.setPlainText("Thinking…")
        self.answer.setPlainText(chat(prompt))

    # Focus the input each time
    def show(self):
        super().show()
        self.query.setFocus()
