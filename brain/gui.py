from datetime import datetime, date
import re
import json
import shutil
from PySide6.QtWidgets import (
    QDialog, QWidget, QTextEdit, QTextBrowser, QVBoxLayout, QLineEdit, QPushButton,
    QHBoxLayout, QSystemTrayIcon, QTableWidget, QTableWidgetItem, QFileDialog,
    QDateEdit, QComboBox, QGridLayout, QGroupBox, QLabel, QProgressBar, QFormLayout, QGraphicsOpacityEffect
)
from PySide6.QtCore import Qt, QSize, QThread, Signal, QDate, QPropertyAnimation
from PySide6.QtGui import QKeySequence, QIcon, QMovie, QFont

from .storage import add, topk, delete, get_note, update_note, export_notes, DB, filter_notes, get_recent_notes, get_favorite_notes, toggle_favorite
from .llm import chat

STYLE_SHEET = """
QWidget {
    font-family: 'Roboto', sans-serif;
    font-size: 14px;
    background-color: #fafafa;
}
QPushButton {
    padding: 8px 16px;
    border-radius: 10px;
    background-color: #4CAF50;
    color: white;
    border: none;
}
QPushButton:hover {
    background-color: #45a049;
}
QLineEdit, QTextEdit, QDateEdit, QComboBox {
    padding: 8px;
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    background-color: white;
}
QTableWidget {
    selection-background-color: #e8f5e9;
    border: 1px solid #e0e0e0;
    alternate-background-color: #f5f5f5;
}
QTableWidget::item:hover {
    background-color: #f0f0f0;
}
QGroupBox {
    font-weight: bold;
    margin-top: 10px;
    padding: 10px;
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    background-color: white;
}
QTextBrowser {
    font-size: 14px;
    padding: 10px;
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    background-color: white;
}
QLabel {
    font-size: 12px;
    color: #757575;
}
"""

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
        self.setWindowTitle("Add Note")
        self.setFixedSize(480, 350)
        self.setStyleSheet(STYLE_SHEET)

        self.text = NoteTextEdit(self)
        self.text.setPlaceholderText("Paste or type your note…")

        self.tags_input = QLineEdit(placeholderText="Tags (comma-separated)")

        # Interactive "Insert Link" button
        insert_link_btn = QPushButton("Insert Link")
        insert_link_btn.setStyleSheet("background-color: #2196F3; color: white;")
        insert_link_btn.clicked.connect(self._insert_link)

        # Explain note linking
        linking_label = QLabel("Use [[note_id]] to link notes (e.g., [[5]])")
        linking_label.setStyleSheet("font-size: 12px; color: #757575;")

        save_btn = QPushButton("Save (⌘S)")
        close_btn = QPushButton("Close")
        save_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        close_btn.setStyleSheet("background-color: #ccc; color: black;")
        save_btn.clicked.connect(self._save_note)
        close_btn.clicked.connect(self.close)

        btn_row = QHBoxLayout()
        btn_row.addWidget(insert_link_btn)
        btn_row.addStretch()
        btn_row.addWidget(save_btn)
        btn_row.addWidget(close_btn)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addWidget(self.text)
        layout.addWidget(self.tags_input)
        layout.addWidget(linking_label)
        layout.addLayout(btn_row)

    def _insert_link(self):
        cursor = self.text.textCursor()
        cursor.insertText("[[note_id]]")
        self.text.setTextCursor(cursor)

    def _save_note(self):
        body = self.text.toPlainText().strip()
        tags = ','.join(tag.strip() for tag in self.tags_input.text().strip().split(',') if tag.strip())
        if body:
            add(body, tags)
            self.tray.showMessage("Second Brain", "Note saved ✔", QSystemTrayIcon.Information, 2000)
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
        self.setFixedSize(480, 350)
        self.setStyleSheet(STYLE_SHEET)

        self.text = NoteTextEdit(self)
        self.text.setPlaceholderText("Paste or type your note…")

        self.tags_input = QLineEdit(placeholderText="Tags (comma-separated)")

        insert_link_btn = QPushButton("Insert Link")
        insert_link_btn.setStyleSheet("background-color: #2196F3; color: white;")
        insert_link_btn.clicked.connect(self._insert_link)

        linking_label = QLabel("Use [[note_id]] to link notes (e.g., [[5]])")
        linking_label.setStyleSheet("font-size: 12px; color: #757575;")

        save_btn = QPushButton("Save (⌘S)")
        close_btn = QPushButton("Close")
        save_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        close_btn.setStyleSheet("background-color: #ccc; color: black;")
        save_btn.clicked.connect(self._save_note)
        close_btn.clicked.connect(self.close)

        btn_row = QHBoxLayout()
        btn_row.addWidget(insert_link_btn)
        btn_row.addStretch()
        btn_row.addWidget(save_btn)
        btn_row.addWidget(close_btn)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addWidget(self.text)
        layout.addWidget(self.tags_input)
        layout.addWidget(linking_label)
        layout.addLayout(btn_row)

        note = get_note(nid)
        if note:
            self.text.setPlainText(note["body"])
            self.tags_input.setText(note["tags"])

    def _insert_link(self):
        cursor = self.text.textCursor()
        cursor.insertText("[[note_id]]")
        self.text.setTextCursor(cursor)

    def _save_note(self):
        body = self.text.toPlainText().strip()
        tags = ','.join(tag.strip() for tag in self.tags_input.text().strip().split(',') if tag.strip())
        if body:
            update_note(self.nid, body, tags)
            self.tray.showMessage("Second Brain", f"Note {self.nid} updated ✔", QSystemTrayIcon.Information, 2000)
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
                self.result.emit("I don’t have that info in my notes.", [])
                return
            ctx_block = "\n".join(f"[[{nid}]] {b}" for nid, b in ctx)
            prompt = (
                "Here are my notes:\n" + ctx_block + "\n\n"
                "Using ONLY these notes, answer the question below. "
                "If the answer isn’t in the notes, say 'I don’t know.' "
                "Cite notes with [[nid]].\n\n"
                f"Question: {self.q}\nAnswer:"
            )
            self.result.emit(chat(prompt), ctx)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ask")
        self.setFixedSize(520, 400)
        self.setStyleSheet(STYLE_SHEET)

        self.query = QLineEdit(placeholderText="Type your question and press ⏎")

        # Grouped filters for clarity
        filter_group = QGroupBox("Filters")
        filter_layout = QFormLayout()
        self.tag_filter = QLineEdit(placeholderText="comma-separated")
        filter_layout.addRow("Tags:", self.tag_filter)
        self.date_start = QDateEdit()
        self.date_start.setDisplayFormat("yyyy-MM-dd")
        self.date_start.setDate(QDate.currentDate().addMonths(-1))
        filter_layout.addRow("From:", self.date_start)
        self.date_end = QDateEdit()
        self.date_end.setDisplayFormat("yyyy-MM-dd")
        self.date_end.setDate(QDate.currentDate())
        filter_layout.addRow("To:", self.date_end)
        filter_group.setLayout(filter_layout)

        # Custom spinner using QLabel and QMovie
        self.spinner = QLabel()
        self.spinner.setAlignment(Qt.AlignCenter)
        self.spinner.setFixedHeight(30)
        self.spinner.hide()
        self.spinner_movie = QMovie("loading.gif")  # Assume you have a loading.gif in the project
        self.spinner.setMovie(self.spinner_movie)

        self.answer = QTextBrowser()
        self.answer.setOpenLinks(False)
        self.answer.anchorClicked.connect(self._popup)

        layout = QVBoxLayout(self)
        layout.addWidget(self.query)
        layout.addWidget(filter_group)
        layout.addWidget(self.spinner)
        layout.addWidget(self.answer)
        self.query.returnPressed.connect(self._ask)
        self._ctx = {}

    def _ask(self):
        q = self.query.text().strip()
        if not q:
            return
        tags = self.tag_filter.text().strip()
        date_start = (datetime(*self.date_start.date().getDate(), 0, 0, 0).timestamp()
                      if self.date_start.date().isValid() else None)
        date_end = (datetime(*self.date_end.date().getDate(), 23, 59, 59).timestamp()
                    if self.date_end.date().isValid() else None)
        self.query.setDisabled(True)
        self.answer.clear()
        self.spinner.show()
        self.spinner_movie.start()
        self.worker = self.Worker(q, tags, date_start, date_end)
        self.worker.result.connect(self._show)
        self.worker.start()

    def _show(self, ans, ctx):
        self.spinner_movie.stop()
        self.spinner.hide()
        self._ctx = {nid: b for nid, b in ctx}
        html = re.sub(r"\[\[(\d+)\]\]", lambda m: f'<a href="{m.group(1)}">[[{m.group(1)}]]</a>', ans)
        self.answer.setHtml(html)
        self.query.setEnabled(True)
        self.query.setFocus()

    def _popup(self, url):
        nid = int(url.toString())
        body = self._ctx.get(nid) or get_note(nid)["body"] if get_note(nid) else "Note not found."
        viewer = NoteViewer(nid, body, self)
        viewer.show()

    def show(self):
        super().show()
        self.query.setFocus()

class BrowseNotes(QWidget):
    def __init__(self, tray):
        super().__init__()
        self.tray = tray
        self.setWindowTitle("Browse Notes")
        self.setMinimumSize(700, 480)
        self.setStyleSheet(STYLE_SHEET)

        # Filter layout using QFormLayout for better alignment
        filter_group = QGroupBox("Filters")
        filter_layout = QFormLayout()
        self.text_filter = QLineEdit(placeholderText="Filter by text…")
        filter_layout.addRow("Text:", self.text_filter)
        self.tag_filter = QLineEdit(placeholderText="comma-separated")
        filter_layout.addRow("Tags:", self.tag_filter)
        self.date_start = QDateEdit()
        self.date_start.setDisplayFormat("yyyy-MM-dd")
        self.date_start.setDate(QDate.currentDate().addMonths(-1))
        filter_layout.addRow("From:", self.date_start)
        self.date_end = QDateEdit()
        self.date_end.setDisplayFormat("yyyy-MM-dd")
        self.date_end.setDate(QDate.currentDate())
        filter_layout.addRow("To:", self.date_end)
        self.view_mode = QComboBox()
        self.view_mode.addItems(["All", "Recent", "Favorites"])
        self.view_mode.currentTextChanged.connect(self.refresh)
        filter_layout.addRow("View:", self.view_mode)
        filter_group.setLayout(filter_layout)

        export_btn = QPushButton("Backup/Export")
        export_btn.clicked.connect(self._export)

        top_layout = QHBoxLayout()
        top_layout.addWidget(filter_group)
        top_layout.addWidget(export_btn)

        self.table = QTableWidget(columnCount=6)
        self.table.setHorizontalHeaderLabels(["ID", "Tags", "Snippet", "", "", "Fav"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.doubleClicked.connect(self._open_note)
        # Tooltips for clarity
        for i, tip in enumerate(["Note ID", "Tags", "Snippet", "Delete", "Edit", "Favorite"]):
            self.table.horizontalHeaderItem(i).setToolTip(tip)

        layout = QVBoxLayout(self)
        layout.addLayout(top_layout)
        layout.addWidget(self.table)

        self.text_filter.textChanged.connect(self.refresh)
        self.tag_filter.textChanged.connect(self.refresh)
        self.date_start.dateChanged.connect(self.refresh)
        self.date_end.dateChanged.connect(self.refresh)
        self._notes = []
        self.refresh()

    def _open_note(self):
        row = self.table.currentRow()
        if row >= 0:
            nid = int(self.table.item(row, 0).text())
            viewer = NoteViewer(nid, parent=self)
            viewer.show()

    def _table_keys(self, event):
        key = event.key()
        row = self.table.currentRow()
        if key in (Qt.Key_Delete, Qt.Key_Backspace) and row >= 0:
            self._delete(int(self.table.item(row, 0).text()))
        elif key in (Qt.Key_Enter, Qt.Key_Return) and row >= 0:
            self._open_note()
        elif key == Qt.Key_F and row >= 0:
            self._toggle_favorite(int(self.table.item(row, 0).text()))
        else:
            super(QTableWidget, self.table).keyPressEvent(event)

    def _toggle_favorite(self, nid):
        is_favorite = toggle_favorite(nid)
        self.refresh()
        status = "added to" if is_favorite else "removed from"
        self.tray.showMessage("Second Brain", f"Note {nid} {status} favorites", QSystemTrayIcon.Information, 2000)

    def refresh(self):
        txt = self.text_filter.text().strip()
        tag_filter = self.tag_filter.text().strip()
        view_mode = self.view_mode.currentText().lower()
        date_start = (datetime(*self.date_start.date().getDate(), 0, 0, 0).timestamp()
                      if self.date_start.date().isValid() else None)
        date_end = (datetime(*self.date_end.date().getDate(), 23, 59, 59).timestamp()
                    if self.date_end.date().isValid() else None)

        if view_mode == "recent":
            self._notes = get_recent_notes(limit=10)
        elif view_mode == "favorites":
            self._notes = get_favorite_notes()
        else:
            self._notes = filter_notes(txt, tag_filter, date_start, date_end)

        self.table.setRowCount(len(self._notes))
        for row, (nid, _, ts, body, tags, is_favorite) in enumerate(self._notes):
            ts_str = datetime.fromtimestamp(ts).strftime("%Y-%m-d %H:%M")
            snippet = body.replace("\n", " ")[:80]
            snippet_item = QTableWidgetItem(f"{ts_str} — {snippet}")
            snippet_item.setData(Qt.UserRole, body)
            self.table.setItem(row, 0, QTableWidgetItem(str(nid)))
            self.table.setItem(row, 1, QTableWidgetItem(tags or ""))
            self.table.setItem(row, 2, snippet_item)
            del_btn = QPushButton()
            del_btn.setIcon(QIcon.fromTheme("edit-delete"))
            del_btn.setFixedWidth(28)
            del_btn.clicked.connect(lambda _, id=nid: self._delete(id))
            self.table.setCellWidget(row, 3, del_btn)
            edit_btn = QPushButton()
            edit_btn.setIcon(QIcon.fromTheme("document-edit"))
            edit_btn.setFixedWidth(28)
            edit_btn.clicked.connect(lambda _, id=nid: self._edit(id))
            self.table.setCellWidget(row, 4, edit_btn)
            fav_btn = QPushButton()
            fav_btn.setIcon(QIcon.fromTheme("emblem-favorite" if is_favorite else "emblem-unreadable"))
            fav_btn.setFixedWidth(28)
            fav_btn.clicked.connect(lambda _, id=nid: self._toggle_favorite(id))
            self.table.setCellWidget(row, 5, fav_btn)
        self.table.resizeColumnsToContents()
        if self._notes:
            self.table.selectRow(0)
        elif any([txt, tag_filter, date_start, date_end, view_mode]):
            self.tray.showMessage("Second Brain", "No notes match the filters", QSystemTrayIcon.Information, 2000)

    def _delete(self, nid):
        delete(nid)
        self.tray.showMessage("Second Brain", f"Note {nid} deleted", QSystemTrayIcon.Information, 2000)
        self.refresh()

    def _edit(self, nid):
        editor = EditNote(self.tray, nid)
        editor.destroyed.connect(self.refresh)
        editor.show()

    def _export(self):
        file_name, selected_filter = QFileDialog.getSaveFileName(
            self, "Backup or Export Notes", "", "SQLite Database (*.db);;JSON File (*.json)"
        )
        if file_name:
            if selected_filter == "SQLite Database (*.db)":
                shutil.copy(str(DB), file_name)
                self.tray.showMessage("Second Brain", "Database backed up ✔", QSystemTrayIcon.Information, 2000)
            elif selected_filter == "JSON File (*.json)":
                notes = export_notes()
                with open(file_name, 'w') as f:
                    json.dump(notes, f, indent=2)
                self.tray.showMessage("Second Brain", "Notes exported to JSON ✔", QSystemTrayIcon.Information, 2000)

class NoteViewer(QDialog):
    def __init__(self, nid, body=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Note {nid}")
        self.setFixedSize(400, 300)
        self.setStyleSheet(STYLE_SHEET)
        self.text = QTextBrowser()
        self.text.setOpenLinks(False)
        self.text.anchorClicked.connect(self._handle_link)

        back_btn = QPushButton("Back")
        back_btn.setStyleSheet("background-color: #ccc; color: black;")
        back_btn.clicked.connect(self.close)

        layout = QVBoxLayout(self)
        layout.addWidget(self.text)
        layout.addWidget(back_btn)

        if body is None:
            note = get_note(nid)
            body = note["body"] if note else "Note not found."
        html = re.sub(r"\[\[(\d+)\]\]", lambda m: f'<a href="{m.group(1)}">[[{m.group(1)}]]</a>', body)
        self.text.setHtml(html)

        # Fade-in animation
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.animation.setDuration(300)
        self.animation.setStartValue(0)
        self.animation.setEndValue(1)
        self.animation.start()

    def _handle_link(self, url):
        nid = int(url.toString())
        viewer = NoteViewer(nid, parent=self)
        viewer.show()