# brain/gui.py
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget,
    QTextEdit,
    QVBoxLayout,
    QLineEdit,
    QPushButton,
    QHBoxLayout,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
)
from PySide6.QtCore import Qt, QSize, QThread, Signal
from PySide6.QtGui import QKeySequence

from .storage import add, topk, all_notes, delete
from .llm import embed, chat


# ─────────────────────────────────────────────
# Custom QTextEdit with ⌘S / Esc handling
# ─────────────────────────────────────────────
class NoteTextEdit(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Save):
            self.parent._save_note()
        elif event.key() == Qt.Key_Escape:
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

        save_btn = QPushButton("Save (⌘S)")
        close_btn = QPushButton("Close")
        save_btn.clicked.connect(self._save_note)
        close_btn.clicked.connect(self.close)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(save_btn)
        btn_row.addWidget(close_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self.text)
        layout.addLayout(btn_row)

    def _save_note(self):
        body = self.text.toPlainText().strip()
        if not body:
            return
        vec = embed(body)
        add(body, vec)
        self.tray.showMessage(
            "Second Brain", "Note saved ✔", QSystemTrayIcon.Information, 2000
        )
        self.text.clear()
        self.text.setFocus()

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

    def show(self):
        super().show()
        self.query.setFocus()


# ─────────────────────────────────────────────
# “Browse & delete” window
# ─────────────────────────────────────────────
class BrowseNotes(QWidget):
    def __init__(self, tray):
        super().__init__()
        self.tray = tray
        self.setWindowTitle("Browse notes")
        self.setFixedSize(QSize(600, 420))

        self.table = QTableWidget(columnCount=3)
        self.table.setHorizontalHeaderLabels(["ID", "Snippet", "Delete"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)

        layout = QVBoxLayout(self)
        layout.addWidget(self.table)
        self.refresh()

    # ---------------------
    def refresh(self):
        notes = all_notes()
        self.table.setRowCount(len(notes))

        for row, (note_id, ts, body) in enumerate(notes):
            ts_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
            snippet = body.replace("\n", " ")[:60]    # ← pre-compute, no backslash in f-string
            preview = f"{ts_str} — {snippet}"

            self.table.setItem(row, 0, QTableWidgetItem(str(note_id)))
            self.table.setItem(row, 1, QTableWidgetItem(preview))

            del_btn = QPushButton("Delete")
            del_btn.clicked.connect(lambda _, nid=note_id: self._delete(nid))
            self.table.setCellWidget(row, 2, del_btn)

        self.table.resizeColumnsToContents()

    # ---------------------
    def _delete(self, nid: int):
        delete(nid)
        self.tray.showMessage(
            "Second Brain",
            f"Note {nid} deleted ✖",
            QSystemTrayIcon.Information,
            2000,
        )
        self.refresh()
