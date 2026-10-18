import os
import subprocess
import shutil
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QScrollArea, QWidget, QGridLayout, QFrame, QCheckBox, 
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox
)
from PyQt5.QtGui import QPixmap, QCursor
from PyQt5.QtCore import Qt
from app.core.config import Config

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
            
            # Action buttons
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
