from datetime import datetime
import re
from PySide6.QtWidgets import (
    QWidget, QTextEdit, QTextBrowser, QVBoxLayout, QLineEdit, QPushButton,
    QHBoxLayout, QSystemTrayIcon, QTableWidget, QTableWidgetItem, QMessageBox,
)
from PySide6.QtCore import Qt, QSize, QThread, Signal, QTimer
from PySide6.QtGui import QKeySequence

from .storage import add, topk, all_notes, delete
from .llm import chat

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
        add(body)
        if hasattr(self.tray, "showMessage"):
            self.tray.showMessage("Second Brain", "Note saved ✔", QSystemTrayIcon.Information, 2000)
        else:
            import rumps
            rumps.notification("Second Brain", "", "Note saved ✔")
        self.text.clear()
        self.text.setFocus()

    def show(self):
        super().show()
        self.text.setFocus()

class Ask(QWidget):
    class Worker(QThread):
        result = Signal(str, list)
        def __init__(self, q):
            super().__init__()
            self.q = q
        def run(self):
            ctx = topk(self.q, k=6)
            if not ctx:
                self.result.emit("I don't have that information in my notes.", [])
                return
            ctx_block = "\n".join(f"[{i}] {b}" for i, b in ctx)
            prompt = (
                "Here are my notes:\n" + ctx_block + "\n\n"
                "Using ONLY these notes, answer the question below. "
                "If the answer is not contained in the notes, respond 'I don't know.' "
                "Cite any notes used by their number.\n\n"
                f"Question: {self.q}\nAnswer:"
            )
            self.result.emit(chat(prompt), ctx)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ask")
        self.setFixedSize(QSize(520, 400))

        self.query = QLineEdit(placeholderText="Type your question and press ⏎")
        self.spinner = QTextEdit(readOnly=True)
        self.spinner.setFixedHeight(30)
        self.spinner.hide()
        self.answer = QTextBrowser()
        self.answer.setOpenLinks(False)
        self.answer.anchorClicked.connect(self._popup)

        layout = QVBoxLayout(self)
        layout.addWidget(self.query)
        layout.addWidget(self.spinner)
        layout.addWidget(self.answer)
        self.query.returnPressed.connect(self._ask)
        self._ctx = {}

    def _ask(self):
        q = self.query.text().strip()
        if not q:
            return
        self.query.setDisabled(True)
        self.answer.clear()
        self.spinner.show()
        self.spinner.setPlainText("Thinking…")
        self.worker = Ask.Worker(q)
        self.worker.result.connect(self._show)
        self.worker.start()

    def _show(self, ans, ctx):
        self.spinner.hide()
        self._ctx = {i: b for i, b in ctx}
        html = re.sub(r"\[(\d+)]", lambda m: f'<a href="{m.group(1)}">[{m.group(1)}]</a>', ans)
        self.answer.setHtml(html)
        self.query.setEnabled(True)
        self.query.setFocus()

    def _popup(self, url):
        nid = int(url.toString())
        body = self._ctx.get(nid, "Note not found.")
        box = QMessageBox(self)
        box.setWindowTitle(f"Note {nid}")
        box.setText(body)
        box.show()
        QTimer.singleShot(20000, box.accept)

    def show(self):
        super().show()
        self.query.setFocus()

class BrowseNotes(QWidget):
    def __init__(self, tray):
        super().__init__()
        self.tray = tray
        self.setWindowTitle("Browse notes")
        self.setFixedSize(QSize(700, 480))

        self.filter = QLineEdit(placeholderText="Filter…")
        self.table = QTableWidget(columnCount=3)
        self.table.setHorizontalHeaderLabels(["ID", "Snippet", ""])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().hide()

        layout = QVBoxLayout(self)
        layout.addWidget(self.filter)
        layout.addWidget(self.table)

        self.filter.textChanged.connect(self.refresh)
        self.table.keyPressEvent = self._table_keys
        self._notes = []
        self.refresh()

    def _table_keys(self, event):
        key = event.key()
        row = self.table.currentRow()
        if key in (Qt.Key_Delete, Qt.Key_Backspace) and row >= 0:
            self._delete(int(self.table.item(row, 0).text()))
        elif key in (Qt.Key_Enter, Qt.Key_Return) and row >= 0:
            nid = int(self.table.item(row, 0).text())
            body = next(b for i, _, _, b in self._notes if i == nid)
            QMessageBox.information(self, f"Note {nid}", body)
        else:
            super(QTableWidget, self.table).keyPressEvent(event)

    def refresh(self):
        txt = self.filter.text().lower()
        self._notes = all_notes()
        if txt:
            self._notes = [r for r in self._notes if txt in r[3].lower()]
        self.table.setRowCount(len(self._notes))
        for row, (nid, _, ts, body) in enumerate(self._notes):
            ts_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
            snippet = body.replace("\n", " ")[:80]
            self.table.setItem(row, 0, QTableWidgetItem(str(nid)))
            self.table.setItem(row, 1, QTableWidgetItem(f"{ts_str} — {snippet}"))
            btn = QPushButton("✖")
            btn.setFixedWidth(28)
            btn.clicked.connect(lambda _, id=nid: self._delete(id))
            self.table.setCellWidget(row, 2, btn)
        self.table.resizeColumnsToContents()
        if self._notes:
            self.table.selectRow(0)

    def _delete(self, nid):
        delete(nid)
        try:
            self.tray.showMessage("Second Brain", f"Note {nid} deleted", QSystemTrayIcon.Information, 2000)
        except AttributeError:
            import rumps
            rumps.notification("Second Brain", "", f"Note {nid} deleted")
        self.refresh()

import requests

OLLAMA = "http://localhost:11434"

def _post_json(path, payload):
    r = requests.post(f"{OLLAMA}{path}", json=payload, timeout=60)
    r.raise_for_status()
    return r.json()

def embed(text: str) -> list[float]:
    data = _post_json(
        "/api/embeddings",
        {"model": "mxbai-embed-large", "prompt": text}
    )
    return data.get("embedding") or data.get("data") or []

def chat(prompt: str) -> str:
    data = _post_json(
        "/api/chat",
        {"model": "llama3:8b",
         "messages": [{"role": "user", "content": prompt}],
         "stream": False}
    )
    return data.get("message", {}).get("content", "")