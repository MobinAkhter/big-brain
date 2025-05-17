# brain/gui.py
from datetime import datetime, date
import re
import json
import shutil
from PySide6.QtWidgets import (
    QDialog, QWidget, QTextEdit, QTextBrowser, QVBoxLayout, QLineEdit, QPushButton,
    QHBoxLayout, QSystemTrayIcon, QTableWidget, QTableWidgetItem, QMessageBox, QFileDialog, QDateEdit
)
from PySide6.QtCore import Qt, QSize, QThread, Signal, QDate
from PySide6.QtGui import QKeySequence

from .storage import add, topk, all_notes, delete, get_note, update_note, export_notes, DB, filter_notes
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
        self.text.setPlaceholderText("Paste or type any snippet… (e.g., See [[5]] for details)")

        self.tags_input = QLineEdit(placeholderText="Tags (comma-separated)")

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
        layout.addWidget(self.tags_input)
        layout.addLayout(btn_row)

    def _save_note(self):
        body = self.text.toPlainText().strip()
        tags_input = self.tags_input.text().strip()
        tags = ','.join(tag.strip() for tag in tags_input.split(',') if tag.strip())
        if body:
            add(body, tags)
            if hasattr(self.tray, "showMessage"):
                self.tray.showMessage("Second Brain", "Note saved ✔", QSystemTrayIcon.Information, 2000)
            else:
                import rumps
                rumps.notification("Second Brain", "", "Note saved ✔")
            self.text.clear()
            self.tags_input.clear()
            self.text.setFocus()

    def show(self):
        super().show()
        self.text.setFocus()


class EditNote(QWidget):
    def __init__(self, tray, nid):
        super().__init__()
        self.tray = tray
        self.nid = nid
        self.setWindowTitle(f"Edit Note {nid}")
        self.setFixedSize(QSize(480, 300))

        self.text = NoteTextEdit(self)
        self.text.setPlaceholderText("Paste or type any snippet… (e.g., See [[5]] for details)")

        self.tags_input = QLineEdit(placeholderText="Tags (comma-separated)")

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
        layout.addWidget(self.tags_input)
        layout.addLayout(btn_row)

        # Load existing note data
        note = get_note(nid)
        if note:
            self.text.setPlainText(note["body"])
            self.tags_input.setText(note["tags"])

    def _save_note(self):
        body = self.text.toPlainText().strip()
        tags_input = self.tags_input.text().strip()
        tags = ','.join(tag.strip() for tag in tags_input.split(',') if tag.strip())
        if body:
            update_note(self.nid, body, tags)
            if hasattr(self.tray, "showMessage"):
                self.tray.showMessage("Second Brain", f"Note {self.nid} updated ✔", QSystemTrayIcon.Information, 2000)
            else:
                import rumps
                rumps.notification("Second Brain", "", f"Note {self.nid} updated ✔")
            self.close()

    def show(self):
        super().show()
        self.text.setFocus()


class Ask(QWidget):
    class Worker(QThread):
        result = Signal(str, list)

        def __init__(self, q, tags, date_start, date_end):
            super().__init__()
            self.q = q
            self.tags = tags
            self.date_start = date_start
            self.date_end = date_end

        def run(self):
            ctx = topk(self.q, k=6, tags=self.tags, date_start=self.date_start, date_end=self.date_end)
            if not ctx:
                self.result.emit("I don't have that information in my notes.", [])
                return
            ctx_block = "\n".join(f"[[{nid}]] {b}" for nid, b in ctx)
            prompt = (
                "Here are my notes:\n" + ctx_block + "\n\n"
                "Using ONLY these notes, answer the question below. "
                "If the answer is not contained in the notes, respond 'I don't know.' "
                "Cite any notes used by their number in double square brackets, like [[nid]].\n\n"
                f"Question: {self.q}\nAnswer:"
            )
            self.result.emit(chat(prompt), ctx)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ask")
        self.setFixedSize(QSize(520, 400))

        self.query = QLineEdit(placeholderText="Type your question and press ⏎")
        self.tag_filter = QLineEdit(placeholderText="Filter by tags (comma-separated)")
        self.date_start = QDateEdit()
        self.date_start.setDisplayFormat("yyyy-MM-dd")
        self.date_start.setDate(QDate.currentDate().addMonths(-1))
        self.date_end = QDateEdit()
        self.date_end.setDisplayFormat("yyyy-MM-dd")
        self.date_end.setDate(QDate.currentDate())

        filter_layout = QHBoxLayout()
        filter_layout.addWidget(self.tag_filter)
        filter_layout.addWidget(self.date_start)
        filter_layout.addWidget(self.date_end)

        self.spinner = QTextEdit(readOnly=True)
        self.spinner.setFixedHeight(30)
        self.spinner.hide()
        self.answer = QTextBrowser()
        self.answer.setOpenLinks(False)
        self.answer.anchorClicked.connect(self._popup)

        layout = QVBoxLayout(self)
        layout.addWidget(self.query)
        layout.addLayout(filter_layout)
        layout.addWidget(self.spinner)
        layout.addWidget(self.answer)
        self.query.returnPressed.connect(self._ask)
        self._ctx = {}

    def _ask(self):
        q = self.query.text().strip()
        if not q:
            return
        tags = self.tag_filter.text().strip()
        if self.date_start.date().isValid():
            qdate = self.date_start.date()
            pydate = date(qdate.year(), qdate.month(), qdate.day())
            date_start = datetime(pydate.year, pydate.month, pydate.day, 0, 0, 0).timestamp()
        else:
            date_start = None

        if self.date_end.date().isValid():
            qdate = self.date_end.date()
            pydate = date(qdate.year(), qdate.month(), qdate.day())
            end_dt = datetime(pydate.year, pydate.month, pydate.day, 23, 59, 59)
            date_end = end_dt.timestamp()
        else:
            date_end = None
        self.query.setDisabled(True)
        self.answer.clear()
        self.spinner.show()
        self.spinner.setPlainText("Thinking…")
        self.worker = Ask.Worker(q, tags, date_start, date_end)
        self.worker.result.connect(self._show)
        self.worker.start()

    def _show(self, ans, ctx):
        self.spinner.hide()
        self._ctx = {nid: b for nid, b in ctx}
        html = re.sub(r"\[\[(\d+)\]\]", lambda m: f'<a href="{m.group(1)}">[[{m.group(1)}]]</a>', ans)
        self.answer.setHtml(html)
        self.query.setEnabled(True)
        self.query.setFocus()

    def _popup(self, url):
        nid = int(url.toString())
        body = self._ctx.get(nid, None)
        if body is None:
            note = get_note(nid)
            body = note["body"] if note else "Note not found."
        viewer = NoteViewer(nid, body=body, parent=self)
        viewer.show()

    def show(self):
        super().show()
        self.query.setFocus()


class BrowseNotes(QWidget):
    def __init__(self, tray):
        super().__init__()
        self.tray = tray
        self.setWindowTitle("Browse notes")
        self.setFixedSize(QSize(700, 480))

        self.text_filter = QLineEdit(placeholderText="Filter by text…")
        self.tag_filter = QLineEdit(placeholderText="Filter by tags (comma-separated)…")
        self.date_start = QDateEdit()
        self.date_start.setDisplayFormat("yyyy-MM-dd")
        self.date_start.setDate(QDate.currentDate().addMonths(-1))
        self.date_end = QDateEdit()
        self.date_end.setDisplayFormat("yyyy-MM-dd")
        self.date_end.setDate(QDate.currentDate())

        export_btn = QPushButton("Backup/Export")
        export_btn.clicked.connect(self._export)

        filter_layout = QHBoxLayout()
        filter_layout.addWidget(self.text_filter)
        filter_layout.addWidget(self.tag_filter)
        filter_layout.addWidget(self.date_start)
        filter_layout.addWidget(self.date_end)
        filter_layout.addWidget(export_btn)

        self.table = QTableWidget(columnCount=5)
        self.table.setHorizontalHeaderLabels(["ID", "Tags", "Snippet", "", ""])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().hide()

        layout = QVBoxLayout(self)
        layout.addLayout(filter_layout)
        layout.addWidget(self.table)

        self.text_filter.textChanged.connect(self.refresh)
        self.tag_filter.textChanged.connect(self.refresh)
        self.date_start.dateChanged.connect(self.refresh)
        self.date_end.dateChanged.connect(self.refresh)
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
            viewer = NoteViewer(nid, parent=self)
            viewer.show()
        else:
            super(QTableWidget, self.table).keyPressEvent(event)

    def refresh(self):
        txt = self.text_filter.text().strip()
        tag_filter = self.tag_filter.text().strip()
        if self.date_start.date().isValid():
            qdate = self.date_start.date()
            pydate = date(qdate.year(), qdate.month(), qdate.day())
            date_start = datetime(pydate.year, pydate.month, pydate.day, 0, 0, 0).timestamp()
        else:
            date_start = None

        if self.date_end.date().isValid():
            qdate = self.date_end.date()
            pydate = date(qdate.year(), qdate.month(), qdate.day())
            end_dt = datetime(pydate.year, pydate.month, pydate.day, 23, 59, 59)
            date_end = end_dt.timestamp()
        else:
            date_end = None
        self._notes = filter_notes(txt, tag_filter, date_start, date_end)
        self.table.setRowCount(len(self._notes))
        for row, (nid, _, ts, body, tags) in enumerate(self._notes):
            ts_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
            snippet = body.replace("\n", " ")[:80]
            snippet_item = QTableWidgetItem(f"{ts_str} — {snippet}")
            snippet_item.setData(Qt.UserRole, body)
            self.table.setItem(row, 0, QTableWidgetItem(str(nid)))
            self.table.setItem(row, 1, QTableWidgetItem(tags or ""))
            self.table.setItem(row, 2, snippet_item)
            del_btn = QPushButton("✖")
            del_btn.setFixedWidth(28)
            del_btn.clicked.connect(lambda _, id=nid: self._delete(id))
            self.table.setCellWidget(row, 3, del_btn)
            edit_btn = QPushButton("✎")
            edit_btn.setFixedWidth(28)
            edit_btn.clicked.connect(lambda _, id=nid: self._edit(id))
            self.table.setCellWidget(row, 4, edit_btn)
        self.table.resizeColumnsToContents()
        if self._notes:
            self.table.selectRow(0)
        elif txt or tag_filter or date_start or date_end:
            if hasattr(self.tray, "showMessage"):
                self.tray.showMessage("Second Brain", "No notes match the filters", QSystemTrayIcon.Information, 2000)
            else:
                import rumps
                rumps.notification("Second Brain", "", "No notes match the filters")

    def _delete(self, nid):
        delete(nid)
        try:
            self.tray.showMessage("Second Brain", f"Note {nid} deleted", QSystemTrayIcon.Information, 2000)
        except AttributeError:
            import rumps
            rumps.notification("Second Brain", "", f"Note {nid} deleted")
        self.refresh()

    def _edit(self, nid):
        editor = EditNote(self.tray, nid)
        editor.destroyed.connect(self.refresh)
        editor.show()

    def _export(self):
        options = QFileDialog.Options()
        file_name, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Backup or Export Notes",
            "",
            "SQLite Database (*.db);;JSON File (*.json)",
            options=options
        )
        if file_name:
            if selected_filter == "SQLite Database (*.db)":
                shutil.copy(str(DB), file_name)
                if hasattr(self.tray, "showMessage"):
                    self.tray.showMessage("Second Brain", "Database backed up ✔", QSystemTrayIcon.Information, 2000)
                else:
                    import rumps
                    rumps.notification("Second Brain", "", "Database backed up ✔")
            elif selected_filter == "JSON File (*.json)":
                notes = export_notes()
                with open(file_name, 'w') as f:
                    json.dump(notes, f, indent=2)
                if hasattr(self.tray, "showMessage"):
                    self.tray.showMessage("Second Brain", "Notes exported to JSON ✔", QSystemTrayIcon.Information, 2000)
                else:
                    import rumps
                    rumps.notification("Second Brain", "", "Notes exported to JSON ✔")


class NoteViewer(QDialog):
    def __init__(self, nid, body=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Note {nid}")
        self.setFixedSize(400, 300)
        self.text = QTextBrowser()
        self.text.setOpenLinks(False)
        self.text.anchorClicked.connect(self._handle_link)
        layout = QVBoxLayout(self)
        layout.addWidget(self.text)
        if body is None:
            note = get_note(nid)
            body = note["body"] if note else "Note not found."
        html = re.sub(r"\[\[(\d+)\]\]", lambda m: f'<a href="{m.group(1)}">[[{m.group(1)}]]</a>', body)
        self.text.setHtml(html)

    def _handle_link(self, url):
        nid = int(url.toString())
        viewer = NoteViewer(nid, parent=self)
        viewer.show()