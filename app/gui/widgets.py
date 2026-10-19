import os
import subprocess
import shutil
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QGridLayout, QFrame, QCheckBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QLineEdit, QApplication
)
from PyQt5.QtGui import QPixmap, QCursor
from PyQt5.QtCore import Qt
from app.core.config import Config
from app.utils.file_utils import get_extension_dir, find_browser_executable


class ScreenshotPreviewDialog(QDialog):
    def __init__(self, image_paths, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pilih Cuplikan (Screenshot) untuk Disimpan")
        self.resize(1000, 700)
        self.setModal(True)
        self.apply_theme()

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(12)

        label = QLabel("Pilih cuplikan gambar yang ingin Anda simpan ke folder tujuan:")
        label.setStyleSheet("font-weight: bold; font-size: 15px; color: #7aa2f7;")
        self.layout.addWidget(label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.grid = QGridLayout(self.scroll_content)
        self.grid.setSpacing(15)
        self.scroll.setWidget(self.scroll_content)
        self.layout.addWidget(self.scroll)

        self.checkboxes = []
        cols = 3
        for i, path in enumerate(image_paths):
            row = i // cols
            col = i % cols

            container = QFrame()
            container.setFrameShape(QFrame.StyledPanel)
            container.setStyleSheet("background-color: #24283b; border-radius: 8px; border: 1px solid #414868;")
            vbox = QVBoxLayout(container)
            vbox.setContentsMargins(8, 8, 8, 8)

            img_label = QLabel()
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                img_label.setPixmap(pixmap.scaled(300, 168, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            img_label.setAlignment(Qt.AlignCenter)
            vbox.addWidget(img_label)

            cb = QCheckBox(f"Simpan Gambar #{i+1}")
            cb.setChecked(True)
            cb.setCursor(QCursor(Qt.PointingHandCursor))
            cb.setProperty("file_path", path)
            vbox.addWidget(cb)
            self.checkboxes.append(cb)
            self.grid.addWidget(container, row, col)

        btn_layout = QHBoxLayout()
        self.btn_select_all = QPushButton("Pilih Semua")
        self.btn_select_all.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_select_all.clicked.connect(self.select_all)

        self.btn_save = QPushButton("Simpan Gambar Terpilih")
        self.btn_save.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_save.setStyleSheet("background-color: #9ece6a; color: #1a1b26; font-weight: bold;")
        self.btn_save.clicked.connect(self.accept)

        self.btn_cancel = QPushButton("Buang Semua Cuplikan")
        self.btn_cancel.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_cancel.setStyleSheet("background-color: #f7768e; color: white;")
        self.btn_cancel.clicked.connect(self.reject)

        btn_layout.addWidget(self.btn_select_all)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_save)
        self.layout.addLayout(btn_layout)

    def select_all(self):
        all_checked = all(cb.isChecked() for cb in self.checkboxes)
        for cb in self.checkboxes:
            cb.setChecked(not all_checked)
        self.btn_select_all.setText("Batal Pilih Semua" if not all_checked else "Pilih Semua")

    def get_selected_files(self):
        selected = []
        for cb in self.checkboxes:
            if cb.isChecked():
                selected.append(cb.property("file_path"))
        return selected

    def apply_theme(self):
        self.setStyleSheet("""
            QDialog { background-color: #1a1b26; }
            QLabel { color: #a9b1d6; font-family: 'Segoe UI'; }
            QScrollArea { border: 1px solid #414868; background-color: transparent; border-radius: 8px; }
            QPushButton { border-radius: 6px; padding: 8px 16px; font-weight: bold; font-size: 13px; background-color: #3d59a1; color: white; }
            QPushButton:hover { opacity: 0.9; }
            QCheckBox { color: #a9b1d6; padding: 4px; font-size: 13px; }
            QCheckBox::indicator { width: 18px; height: 18px; }
        """)


class HistoryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Riwayat Unduhan - Kawaragi Downloader")
        self.resize(850, 500)
        self.setModal(True)
        self.apply_theme()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title_label = QLabel("📁 Riwayat Unduhan Terakhir")
        title_label.setStyleSheet("font-weight: bold; font-size: 16px; color: #7aa2f7;")
        layout.addWidget(title_label)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Judul Video", "Waktu Selesai", "Lokasi File", "Aksi"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)

        self.load_data()

        bottom_layout = QHBoxLayout()
        btn_clear = QPushButton("🗑️ Bersihkan Riwayat")
        btn_clear.setStyleSheet("background-color: #f7768e; color: white;")
        btn_clear.clicked.connect(self.clear_all)

        btn_close = QPushButton("Tutup")
        btn_close.clicked.connect(self.accept)

        bottom_layout.addWidget(btn_clear)
        bottom_layout.addStretch()
        bottom_layout.addWidget(btn_close)
        layout.addLayout(bottom_layout)

    def load_data(self):
        history = Config.load_history()
        self.table.setRowCount(len(history))
        for row, item in enumerate(history):
            title = item.get("title", "Tidak ada judul")
            ts = item.get("timestamp", "-")
            path = item.get("file_path", "")

            self.table.setItem(row, 0, QTableWidgetItem(title))
            self.table.setItem(row, 1, QTableWidgetItem(ts))
            self.table.setItem(row, 2, QTableWidgetItem(path))

            btn_box = QWidget()
            h = QHBoxLayout(btn_box)
            h.setContentsMargins(2, 2, 2, 2)
            h.setSpacing(4)

            btn_play = QPushButton("▶ Buka")
            btn_play.setStyleSheet("padding: 4px 8px; font-size: 11px; background-color: #7aa2f7; color: #1a1b26;")
            btn_play.clicked.connect(lambda _, p=path: self.open_file(p))

            btn_folder = QPushButton("📂 Folder")
            btn_folder.setStyleSheet("padding: 4px 8px; font-size: 11px; background-color: #bb9af7; color: #1a1b26;")
            btn_folder.clicked.connect(lambda _, p=path: self.open_folder(p))

            h.addWidget(btn_play)
            h.addWidget(btn_folder)
            self.table.setCellWidget(row, 3, btn_box)

    def open_file(self, path):
        if os.path.exists(path):
            os.startfile(path)
        else:
            QMessageBox.warning(self, "File Hilang", f"File tidak ditemukan di:\n{path}")

    def open_folder(self, path):
        folder = os.path.dirname(path) if os.path.isfile(path) else path
        if os.path.exists(folder):
            if os.path.isfile(path):
                subprocess.run(f'explorer /select,"{os.path.normpath(path)}"', shell=True)
            else:
                os.startfile(folder)
        else:
            QMessageBox.warning(self, "Folder Hilang", f"Folder tidak ditemukan di:\n{folder}")

    def clear_all(self):
        confirm = QMessageBox.question(self, "Konfirmasi", "Yakin ingin menghapus seluruh riwayat unduhan?", QMessageBox.Yes | QMessageBox.No)
        if confirm == QMessageBox.Yes:
            Config.clear_history()
            self.table.setRowCount(0)

    def apply_theme(self):
        self.setStyleSheet("""
            QDialog { background-color: #1a1b26; }
            QLabel { color: #a9b1d6; font-family: 'Segoe UI'; }
            QTableWidget { background-color: #24283b; color: #c0caf5; border: 1px solid #414868; border-radius: 8px; gridline-color: #414868; }
            QHeaderView::section { background-color: #1f2335; color: #7aa2f7; padding: 6px; border: 1px solid #414868; font-weight: bold; }
            QPushButton { border-radius: 6px; padding: 8px 16px; font-weight: bold; font-size: 13px; background-color: #3d59a1; color: white; }
        """)


class ExtensionHelperDialog(QDialog):
    """Dialog asisten untuk memasang dan mengaktifkan ekstensi Kawaragi-Trigger dengan 1 klik."""
    def __init__(self, is_connected=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Asisten Pemasangan Ekstensi Browser - Kawaragi Trigger")
        self.resize(680, 480)
        self.setModal(True)
        self.ext_dir = get_extension_dir()
        self.apply_theme()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)

        title = QLabel("🧩 Pasang & Hubungkan Ekstensi Kawaragi Trigger")
        title.setStyleSheet("font-weight: bold; font-size: 17px; color: #7aa2f7;")
        layout.addWidget(title)

        status_text = (
            "🟢 <b>Status Saat Ini: TERHUBUNG!</b> Ekstensi Chrome/Edge sudah aktif dan siap menyinkronkan cookies."
            if is_connected else
            "🟡 <b>Status Saat Ini: BELUM TERHUBUNG.</b> Ikuti salah satu cara cepat di bawah ini untuk mengaktifkan jembatan ekstensi:"
        )
        status_lbl = QLabel(status_text)
        status_lbl.setWordWrap(True)
        status_lbl.setStyleSheet(
            f"background-color: #24283b; border: 1px solid {'#9ece6a' if is_connected else '#e0af68'}; "
            f"border-radius: 8px; padding: 10px; color: {'#9ece6a' if is_connected else '#e0af68'};"
        )
        layout.addWidget(status_lbl)

        # Lokasi Folder Ekstensi
        path_lbl = QLabel("📍 Lokasi Folder Ekstensi (Otomatis Disalin saat klik tombol di bawah):")
        path_lbl.setStyleSheet("font-weight: bold; color: #c0caf5;")
        layout.addWidget(path_lbl)

        path_row = QHBoxLayout()
        self.path_edit = QLineEdit(self.ext_dir)
        self.path_edit.setReadOnly(True)
        path_row.addWidget(self.path_edit)

        btn_copy_path = QPushButton("📋 Salin Path")
        btn_copy_path.setCursor(QCursor(Qt.PointingHandCursor))
        btn_copy_path.clicked.connect(self.copy_ext_path)
        path_row.addWidget(btn_copy_path)

        btn_open_folder = QPushButton("📂 Buka Folder")
        btn_open_folder.setCursor(QCursor(Qt.PointingHandCursor))
        btn_open_folder.clicked.connect(self.open_ext_folder)
        path_row.addWidget(btn_open_folder)
        layout.addLayout(path_row)

        # Panduan Langkah Cepat
        guide_frame = QFrame()
        guide_frame.setStyleSheet("background-color: #24283b; border: 1px solid #414868; border-radius: 8px; padding: 10px;")
        guide_layout = QVBoxLayout(guide_frame)
        guide_text = QLabel(
            "<b>Cara Pasang Super Cepat (Hanya 10 Detik):</b><br>"
            "1. Klik tombol <b>'Pasang ke Google Chrome'</b> atau <b>'Pasang ke Microsoft Edge'</b> di bawah.<br>"
            "   <i>(Path folder ekstensi sudah otomatis disalin ke Clipboard &amp; jendela folder akan terbuka).</i><br>"
            "2. Di halaman Ekstensi browser yang terbuka, nyalakan <b>Developer mode (Mode Pengembang)</b> di pojok atas.<br>"
            "3. <b>Seret &amp; Lepas (Drag &amp; Drop)</b> folder <code>Kawaragi-Trigger</code> langsung ke halaman browser tersebut, "
            "ATAU klik <b>Load unpacked (Muat yang belum dikemas)</b> lalu tekan <code>Ctrl + V</code> dan Enter!"
        )
        guide_text.setWordWrap(True)
        guide_layout.addWidget(guide_text)
        layout.addWidget(guide_frame)

        # Tombol Aksi 1-Klik
        btn_grid = QGridLayout()
        btn_grid.setSpacing(10)

        btn_chrome = QPushButton("🌐 Pasang ke Google Chrome (Buka chrome://extensions)")
        btn_chrome.setCursor(QCursor(Qt.PointingHandCursor))
        btn_chrome.setStyleSheet("background-color: #9ece6a; color: #1a1b26; padding: 11px;")
        btn_chrome.clicked.connect(lambda: self.install_to_browser("chrome"))
        btn_grid.addWidget(btn_chrome, 0, 0)

        btn_edge = QPushButton("🧭 Pasang ke Microsoft Edge (Buka edge://extensions)")
        btn_edge.setCursor(QCursor(Qt.PointingHandCursor))
        btn_edge.setStyleSheet("background-color: #7aa2f7; color: #1a1b26; padding: 11px;")
        btn_edge.clicked.connect(lambda: self.install_to_browser("edge"))
        btn_grid.addWidget(btn_edge, 0, 1)

        btn_auto_launch = QPushButton("⚡ Luncurkan Browser Khusus dengan Ekstensi Langsung Aktif (Otomatis)")
        btn_auto_launch.setCursor(QCursor(Qt.PointingHandCursor))
        btn_auto_launch.setStyleSheet("background-color: #bb9af7; color: #1a1b26; padding: 11px;")
        btn_auto_launch.clicked.connect(self.launch_browser_with_extension)
        btn_grid.addWidget(btn_auto_launch, 1, 0, 1, 2)

        layout.addLayout(btn_grid)
        layout.addStretch()

        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        btn_close = QPushButton("Tutup")
        btn_close.clicked.connect(self.accept)
        bottom_row.addWidget(btn_close)
        layout.addLayout(bottom_row)

    def copy_ext_path(self):
        QApplication.clipboard().setText(self.ext_dir)
        QMessageBox.information(self, "Tersalin", f"Path folder ekstensi berhasil disalin ke Clipboard:\n\n{self.ext_dir}")

    def open_ext_folder(self):
        QApplication.clipboard().setText(self.ext_dir)
        if os.path.exists(self.ext_dir):
            subprocess.run(f'explorer /select,"{os.path.normpath(self.ext_dir)}"', shell=True)
        else:
            QMessageBox.warning(self, "Folder Tidak Ditemukan", f"Folder ekstensi tidak ditemukan di:\n{self.ext_dir}")

    def install_to_browser(self, browser_type: str):
        QApplication.clipboard().setText(self.ext_dir)
        # Buka Explorer menyorot folder Kawaragi-Trigger agar mudah di-drag & drop
        if os.path.exists(self.ext_dir):
            subprocess.run(f'explorer /select,"{os.path.normpath(self.ext_dir)}"', shell=True)

        exe_path = find_browser_executable(browser_type)
        ext_url = "edge://extensions" if browser_type == "edge" else "chrome://extensions"

        if exe_path:
            try:
                subprocess.Popen([exe_path, ext_url])
            except Exception:
                pass
        else:
            # Fallback ke browser default
            for b in ("chrome", "edge", "brave"):
                p = find_browser_executable(b)
                if p:
                    subprocess.Popen([p, "chrome://extensions"])
                    break

        QMessageBox.information(
            self,
            "Siap Dipasang!",
            f"1. Path ekstensi sudah disalin ke Clipboard:\n   {self.ext_dir}\n\n"
            f"2. Di jendela browser yang terbuka, aktifkan 'Developer mode' (Mode Pengembang).\n"
            f"3. Klik 'Load unpacked' (Muat yang belum dikemas) lalu tekan Ctrl+V dan Enter,\n"
            f"   ATAU seret folder 'Kawaragi-Trigger' dari Explorer langsung ke halaman ekstensi browser!"
        )

    def launch_browser_with_extension(self):
        """Meluncurkan Chrome/Edge dengan flag --load-extension agar ekstensi langsung aktif otomatis."""
        exe_path = find_browser_executable("chrome") or find_browser_executable("edge") or find_browser_executable("brave")
        if not exe_path:
            QMessageBox.warning(self, "Browser Tidak Ditemukan", "Google Chrome, Microsoft Edge, atau Brave tidak ditemukan di komputer ini.")
            return

        profile_dir = os.path.join(Config.get_app_data_dir(), "BrowserProfile")
        os.makedirs(profile_dir, exist_ok=True)
        try:
            subprocess.Popen([
                exe_path,
                f"--user-data-dir={profile_dir}",
                f"--load-extension={self.ext_dir}",
                "--no-first-run",
                "https://www.youtube.com"
            ])
        except Exception as e:
            QMessageBox.warning(self, "Gagal Meluncurkan Browser", str(e))

    def apply_theme(self):
        self.setStyleSheet("""
            QDialog { background-color: #1a1b26; }
            QLabel { color: #c0caf5; font-family: 'Segoe UI'; font-size: 13px; }
            QLineEdit { background-color: #1f2335; color: #7aa2f7; border: 1px solid #414868; border-radius: 6px; padding: 7px; font-family: 'Consolas', monospace; }
            QPushButton { border-radius: 6px; padding: 8px 14px; font-weight: bold; font-size: 13px; background-color: #3d59a1; color: white; border: none; }
            QPushButton:hover { opacity: 0.9; }
        """)
