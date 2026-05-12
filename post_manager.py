# Nama  : Pudael Zikri
# NIM   : F1D02310088
# Kelas : C

import sys
import json
import urllib.request
import urllib.error
import urllib.parse

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QLabel, QPushButton, QLineEdit,
    QTextEdit, QComboBox, QSplitter, QFrame, QDialog, QDialogButtonBox,
    QMessageBox, QHeaderView, QAbstractItemView, QFormLayout, QScrollArea,
    QStatusBar, QGroupBox
)
from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtGui import QFont, QColor

BASE_URL = "https://api.pahrul.my.id/api/posts"

class ApiWorker(QObject):
    finished = Signal(object)   
    error    = Signal(str)     

    def __init__(self, method: str, url: str, payload: dict = None):
        super().__init__()
        self.method  = method.upper()
        self.url     = url
        self.payload = payload

    def run(self):
        try:
            data = json.dumps(self.payload).encode("utf-8") if self.payload else None
            req  = urllib.request.Request(self.url, data=data, method=self.method)
            req.add_header("Content-Type", "application/json")
            req.add_header("Accept", "application/json")

            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read().decode("utf-8")
                result = json.loads(body) if body.strip() else {}
                self.finished.emit(result)

        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode("utf-8")
                detail = json.loads(body)
                if e.code == 422 and "detail" in detail:
                    msgs = []
                    for d in detail["detail"]:
                        msgs.append(d.get("msg", str(d)))
                    self.error.emit("Validasi gagal:\n" + "\n".join(msgs))
                else:
                    self.error.emit(f"HTTP {e.code}: {detail.get('detail', body)}")
            except Exception:
                self.error.emit(f"HTTP Error {e.code}: {e.reason}")
        except urllib.error.URLError as e:
            self.error.emit(f"Koneksi gagal: {e.reason}")
        except TimeoutError:
            self.error.emit("Request timeout. Periksa koneksi internet.")
        except Exception as e:
            self.error.emit(f"Error: {str(e)}")


def run_in_thread(method, url, payload=None, on_success=None, on_error=None):
    """Helper: buat worker + thread, hubungkan sinyal, jalankan."""
    thread = QThread()
    worker = ApiWorker(method, url, payload)
    worker.moveToThread(thread)
    
    thread.worker = worker

    thread.started.connect(worker.run)

    if on_success:
        worker.finished.connect(on_success)
    if on_error:
        worker.error.connect(on_error)

    worker.finished.connect(thread.quit)
    worker.error.connect(thread.quit)
    worker.finished.connect(worker.deleteLater)
    worker.error.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)

    thread.start()
    return thread  

class PostDialog(QDialog):
    def __init__(self, parent=None, post_data: dict = None):
        super().__init__(parent)
        self.setWindowTitle("Tambah Post" if post_data is None else "Edit Post")
        self.setMinimumWidth(480)
        self.setModal(True)

        layout = QVBoxLayout(self)
        form   = QFormLayout()
        form.setSpacing(10)

        self.title_input  = QLineEdit()
        self.author_input = QLineEdit()
        self.slug_input   = QLineEdit()
        self.status_input = QComboBox()
        self.status_input.addItems(["published", "draft"])
        self.body_input   = QTextEdit()
        self.body_input.setMinimumHeight(120)

        form.addRow("Judul *",   self.title_input)
        form.addRow("Author *",  self.author_input)
        form.addRow("Slug *",    self.slug_input)
        form.addRow("Status *",  self.status_input)
        form.addRow("Konten *",  self.body_input)

        if post_data:
            self.title_input.setText(post_data.get("title", ""))
            self.author_input.setText(post_data.get("author", ""))
            self.slug_input.setText(post_data.get("slug", ""))
            idx = self.status_input.findText(post_data.get("status", "draft"))
            if idx >= 0:
                self.status_input.setCurrentIndex(idx)
            self.body_input.setText(post_data.get("body", ""))

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._validate)
        btn_box.rejected.connect(self.reject)

        layout.addLayout(form)
        layout.addWidget(btn_box)

    def _validate(self):
        if not self.title_input.text().strip():
            QMessageBox.warning(self, "Validasi", "Judul tidak boleh kosong.")
            return
        if not self.author_input.text().strip():
            QMessageBox.warning(self, "Validasi", "Author tidak boleh kosong.")
            return
        if not self.slug_input.text().strip():
            QMessageBox.warning(self, "Validasi", "Slug tidak boleh kosong.")
            return
        if not self.body_input.toPlainText().strip():
            QMessageBox.warning(self, "Validasi", "Konten tidak boleh kosong.")
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "title":  self.title_input.text().strip(),
            "author": self.author_input.text().strip(),
            "slug":   self.slug_input.text().strip(),
            "status": self.status_input.currentText(),
            "body":   self.body_input.toPlainText().strip(),
        }



class PostManager(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Post Manager — Pudael Zikri")
        self.setMinimumSize(1100, 650)

        self._threads = []  
        self._selected_post = None

        self._build_ui()
        self._apply_style()
        self.load_posts()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        header = QLabel("Post Manager")
        header.setObjectName("header")
        root.addWidget(header)

        toolbar = QHBoxLayout()
        self.btn_refresh = QPushButton("🔄  Refresh")
        self.btn_add     = QPushButton("➕  Tambah Post")
        self.btn_edit    = QPushButton("✏️  Edit Post")
        self.btn_delete  = QPushButton("🗑️  Hapus Post")

        self.btn_edit.setEnabled(False)
        self.btn_delete.setEnabled(False)

        self.btn_refresh.clicked.connect(self.load_posts)
        self.btn_add.clicked.connect(self.add_post)
        self.btn_edit.clicked.connect(self.edit_post)
        self.btn_delete.clicked.connect(self.delete_post)

        for btn in [self.btn_refresh, self.btn_add, self.btn_edit, self.btn_delete]:
            toolbar.addWidget(btn)
        toolbar.addStretch()
        root.addLayout(toolbar)

        splitter = QSplitter(Qt.Horizontal)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["ID", "Judul", "Author", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self._on_row_selected)
        splitter.addWidget(self.table)

        detail_frame = QFrame()
        detail_frame.setObjectName("detailFrame")
        detail_layout = QVBoxLayout(detail_frame)
        detail_layout.setContentsMargins(12, 12, 12, 12)

        lbl_detail = QLabel("Detail Post")
        lbl_detail.setObjectName("sectionLabel")
        detail_layout.addWidget(lbl_detail)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        self.detail_widget = QWidget()
        self.detail_inner  = QVBoxLayout(self.detail_widget)
        self.detail_inner.setAlignment(Qt.AlignTop)

        self.lbl_title   = QLabel("-")
        self.lbl_title.setWordWrap(True)
        self.lbl_title.setObjectName("detailTitle")
        self.lbl_author  = QLabel("-")
        self.lbl_slug    = QLabel("-")
        self.lbl_status  = QLabel("-")
        self.lbl_body    = QLabel("-")
        self.lbl_body.setWordWrap(True)
        self.lbl_body.setAlignment(Qt.AlignTop)

        self.group_comments = QGroupBox("Komentar")
        self.comments_layout = QVBoxLayout(self.group_comments)
        self.lbl_no_comment  = QLabel("Tidak ada komentar.")
        self.lbl_no_comment.setAlignment(Qt.AlignCenter)
        self.comments_layout.addWidget(self.lbl_no_comment)

        def row(label, widget):
            h = QHBoxLayout()
            lbl = QLabel(f"<b>{label}:</b>")
            lbl.setMinimumWidth(65)
            h.addWidget(lbl)
            h.addWidget(widget, 1)
            return h

        self.detail_inner.addLayout(row("Judul",   self.lbl_title))
        self.detail_inner.addLayout(row("Author",  self.lbl_author))
        self.detail_inner.addLayout(row("Slug",    self.lbl_slug))
        self.detail_inner.addLayout(row("Status",  self.lbl_status))

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        self.detail_inner.addWidget(sep)
        self.detail_inner.addWidget(QLabel("<b>Konten:</b>"))
        self.detail_inner.addWidget(self.lbl_body)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.HLine)
        self.detail_inner.addWidget(sep2)
        self.detail_inner.addWidget(self.group_comments)

        scroll.setWidget(self.detail_widget)
        detail_layout.addWidget(scroll)
        splitter.addWidget(detail_frame)

        splitter.setSizes([700, 400])
        root.addWidget(splitter, 1)  

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Siap.")

    def _apply_style(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #f5f6fa;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 13px;
                color: #2d3436;
            }
            QLabel#header {
                font-size: 20px;
                font-weight: bold;
                color: #0984e3;
                padding: 4px 0;
            }
            QLabel#sectionLabel {
                font-size: 14px;
                font-weight: bold;
                color: #0984e3;
                margin-bottom: 6px;
            }
            QLabel#detailTitle {
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton {
                padding: 7px 16px;
                border-radius: 6px;
                border: none;
                background-color: #0984e3;
                color: white;
                font-weight: bold;
            }
            QPushButton:hover   { background-color: #0773c5; }
            QPushButton:pressed { background-color: #065a9e; }
            QPushButton:disabled {
                background-color: #b2bec3;
                color: #636e72;
            }
            QTableWidget {
                background-color: white;
                border: 1px solid #dfe6e9;
                border-radius: 6px;
                gridline-color: #f0f0f0;
            }
            QTableWidget::item:selected {
                background-color: #74b9ff;
                color: #2d3436;
            }
            QHeaderView::section {
                background-color: #0984e3;
                color: white;
                padding: 6px;
                font-weight: bold;
                border: none;
            }
            QFrame#detailFrame {
                background-color: white;
                border: 1px solid #dfe6e9;
                border-radius: 6px;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #dfe6e9;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                color: #636e72;
            }
            QLineEdit, QTextEdit, QComboBox {
                border: 1px solid #b2bec3;
                border-radius: 4px;
                padding: 5px 8px;
                background-color: white;
            }
            QLineEdit:focus, QTextEdit:focus {
                border-color: #0984e3;
            }
            QStatusBar {
                background-color: #dfe6e9;
                color: #636e72;
                font-size: 12px;
            }
        """)

    def _set_loading(self, loading: bool):
        self.btn_refresh.setEnabled(not loading)
        self.btn_add.setEnabled(not loading)
        if loading:
            self.status_bar.showMessage("⏳ Memuat data...")
        else:
            self.status_bar.showMessage("Siap.")

    def _show_error(self, msg: str):
        self._set_loading(False)
        self.status_bar.showMessage(f"❌ {msg}")
        QMessageBox.critical(self, "Error", msg)

    def _run(self, method, url, payload=None, on_success=None):
        """Jalankan request di thread terpisah."""
        self._set_loading(True)
        t = run_in_thread(
            method, url, payload,
            on_success=on_success,
            on_error=self._show_error
        )
        
        self._threads.append(t)
        t.finished.connect(lambda th=t: self._threads.remove(th) if th in self._threads else None)

    def load_posts(self):
        self._run("GET", BASE_URL, on_success=self._on_posts_loaded)

    def _on_posts_loaded(self, data):
        self._set_loading(False)
        posts = data if isinstance(data, list) else data.get("data", [])
        self.table.setRowCount(0)
        for post in posts:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(post.get("id", ""))))
            self.table.setItem(row, 1, QTableWidgetItem(post.get("title", "")))
            self.table.setItem(row, 2, QTableWidgetItem(post.get("author", "")))

            status_item = QTableWidgetItem(post.get("status", ""))
            color = QColor("#00b894") if post.get("status") == "published" else QColor("#fdcb6e")
            status_item.setForeground(color)
            status_item.setFont(QFont("Segoe UI", 12, QFont.Bold))
            self.table.setItem(row, 3, status_item)

            self.table.item(row, 0).setData(Qt.UserRole, post)

        self.status_bar.showMessage(f"✅ {len(posts)} post dimuat.")
        self._clear_detail()

    def _on_row_selected(self):
        rows = self.table.selectedItems()
        if not rows:
            self.btn_edit.setEnabled(False)
            self.btn_delete.setEnabled(False)
            self._clear_detail()
            return

        self.btn_edit.setEnabled(True)
        self.btn_delete.setEnabled(True)

        post = self.table.item(self.table.currentRow(), 0).data(Qt.UserRole)
        self._selected_post = post
        post_id = post.get("id")
        self._run("GET", f"{BASE_URL}/{post_id}", on_success=self._on_detail_loaded)

    def _on_detail_loaded(self, data):
        self._set_loading(False)
        post = data if isinstance(data, dict) and "title" in data else data.get("data", data)
        self._selected_post = post

        self.lbl_title.setText(post.get("title", "-"))
        self.lbl_author.setText(post.get("author", "-"))
        self.lbl_slug.setText(post.get("slug", "-"))

        status = post.get("status", "-")
        self.lbl_status.setText(status)
        color = "#00b894" if status == "published" else "#e17055"
        self.lbl_status.setStyleSheet(f"color: {color}; font-weight: bold;")

        self.lbl_body.setText(post.get("body", "-"))

        comments = post.get("comments", [])
        for i in reversed(range(self.comments_layout.count())):
            w = self.comments_layout.itemAt(i).widget()
            if w:
                w.setParent(None)

        if not comments:
            self.lbl_no_comment = QLabel("Tidak ada komentar.")
            self.lbl_no_comment.setAlignment(Qt.AlignCenter)
            self.comments_layout.addWidget(self.lbl_no_comment)
        else:
            for c in comments:
                text = f"<b>{c.get('author', 'Anonim')}</b>: {c.get('body', '')}"
                lbl  = QLabel(text)
                lbl.setWordWrap(True)
                lbl.setStyleSheet("padding: 4px; border-bottom: 1px solid #f0f0f0;")
                self.comments_layout.addWidget(lbl)

    def _clear_detail(self):
        self._selected_post = None
        self.lbl_title.setText("-")
        self.lbl_author.setText("-")
        self.lbl_slug.setText("-")
        self.lbl_status.setText("-")
        self.lbl_status.setStyleSheet("")
        self.lbl_body.setText("-")
        for i in reversed(range(self.comments_layout.count())):
            w = self.comments_layout.itemAt(i).widget()
            if w:
                w.setParent(None)
        lbl = QLabel("Tidak ada komentar.")
        lbl.setAlignment(Qt.AlignCenter)
        self.comments_layout.addWidget(lbl)

    def add_post(self):
        dlg = PostDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        payload = dlg.get_data()
        self._run("POST", BASE_URL, payload=payload, on_success=self._on_add_success)

    def _on_add_success(self, data):
        self._set_loading(False)
        new_id = data.get("id", "?") if isinstance(data, dict) else "?"
        QMessageBox.information(self, "Berhasil", f"Post berhasil ditambahkan!\nID: {new_id}")
        self.load_posts()

    def edit_post(self):
        if not self._selected_post:
            return
        dlg = PostDialog(self, self._selected_post)
        if dlg.exec() != QDialog.Accepted:
            return
        payload = dlg.get_data()
        post_id = self._selected_post.get("id")
        self._run("PUT", f"{BASE_URL}/{post_id}", payload=payload, on_success=self._on_edit_success)

    def _on_edit_success(self, data):
        self._set_loading(False)
        QMessageBox.information(self, "Berhasil", "Post berhasil diperbarui!")
        self.load_posts()

    def delete_post(self):
        if not self._selected_post:
            return
        post_id    = self._selected_post.get("id")
        post_title = self._selected_post.get("title", "")
        confirm = QMessageBox.question(
            self, "Konfirmasi Hapus",
            f"Yakin ingin menghapus post:\n\"{post_title}\"?\n\n"
            f"Semua komentar pada post ini juga akan ikut terhapus (cascade delete).",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return
        self._run("DELETE", f"{BASE_URL}/{post_id}", on_success=self._on_delete_success)

    def _on_delete_success(self, data):
        self._set_loading(False)
        QMessageBox.information(self, "Berhasil", "Post berhasil dihapus!")
        self._clear_detail()
        self.btn_edit.setEnabled(False)
        self.btn_delete.setEnabled(False)
        self.load_posts()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = PostManager()
    window.show()
    sys.exit(app.exec())
