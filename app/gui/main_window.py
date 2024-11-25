from PyQt5.QtWidgets import (
    QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, QPushButton, QLineEdit, QLabel, QComboBox, QCheckBox, QFileDialog, QProgressBar, QMessageBox
)
from PyQt5.QtGui import QPixmap
from app.core.downloader import Downloader
from app.utils.validation import is_valid_url
from app.core.config import Config
from app.utils.log_utils import setup_logger

logger = setup_logger("main_window", "app.log")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Kawaragi Downloader")
        self.resize(800, 600)
        
        # Widget Utama
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        # Layout
        self.layout = QVBoxLayout()
        self.central_widget.setLayout(self.layout)
        
        # Header (Logo + Nama Aplikasi)
        self.header_layout = QHBoxLayout()
        self.logo_label = QLabel()
        pixmap = QPixmap("assets/logo.png")
        self.logo_label.setPixmap(pixmap)
        self.logo_label.setFixedSize(50, 50)  # Skala 1:1
        self.logo_label.setScaledContents(True)
        self.header_layout.addWidget(self.logo_label)
        
        self.app_name_label = QLabel("Kawaragi Downloader")
        self.app_name_label.setStyleSheet("font-size: 20px; font-weight: bold;")
        self.header_layout.addWidget(self.app_name_label)
        self.layout.addLayout(self.header_layout)
        
        # Input URL
        self.url_label = QLabel("Masukkan URL:")
        self.layout.addWidget(self.url_label)
        self.url_input = QLineEdit()
        self.layout.addWidget(self.url_input)
        
        # Tombol untuk mendapatkan info video
        self.info_button = QPushButton("Dapatkan Info Video")
        self.info_button.clicked.connect(self.get_video_info)
        self.layout.addWidget(self.info_button)
        
        # Area untuk menampilkan info video
        self.video_info_label = QLabel("Info Video:")
        self.layout.addWidget(self.video_info_label)
        self.video_info = QLabel()
        self.layout.addWidget(self.video_info)
        
        # Dropdown untuk Pilihan Format
        self.format_label = QLabel("Pilih Format:")
        self.layout.addWidget(self.format_label)
        self.format_dropdown = QComboBox()
        self.format_dropdown.addItems(["Otomatis", "Video (MP4)", "Video (WebM)", "Audio (MP3)", "Audio (AAC)"])
        self.layout.addWidget(self.format_dropdown)
        
        # Checkbox untuk Subtitle
        self.subtitle_checkbox = QCheckBox("Unduh Subtitle")
        self.layout.addWidget(self.subtitle_checkbox)
        
        # Dropdown Bahasa Subtitle
        self.subtitle_language_label = QLabel("Pilih Bahasa Subtitle:")
        self.layout.addWidget(self.subtitle_language_label)
        self.subtitle_language_dropdown = QComboBox()
        self.layout.addWidget(self.subtitle_language_dropdown)
        
        # Dropdown Format Subtitle
        self.subtitle_format_label = QLabel("Pilih Format Subtitle:")
        self.layout.addWidget(self.subtitle_format_label)
        self.subtitle_format_dropdown = QComboBox()
        self.subtitle_format_dropdown.addItems(["srt", "vtt", "ass"])
        self.layout.addWidget(self.subtitle_format_dropdown)
        
        # Checkbox untuk Thumbnail
        self.thumbnail_checkbox = QCheckBox("Unduh Thumbnail")
        self.layout.addWidget(self.thumbnail_checkbox)
        
        # Dropdown Format Thumbnail
        self.thumbnail_format_label = QLabel("Pilih Format Thumbnail:")
        self.layout.addWidget(self.thumbnail_format_label)
        self.thumbnail_format_dropdown = QComboBox()
        self.thumbnail_format_dropdown.addItems(["jpg", "png", "webp"])
        self.layout.addWidget(self.thumbnail_format_dropdown)
        
        # Pilihan Direktori Penyimpanan
        self.directory_label = QLabel("Direktori Penyimpanan:")
        self.layout.addWidget(self.directory_label)
        self.directory_path = QLineEdit()
        self.directory_path.setText(Config.load_last_directory())  # Load direktori terakhir
        self.layout.addWidget(self.directory_path)
        self.browse_button = QPushButton("Pilih Direktori")
        self.browse_button.clicked.connect(self.choose_directory)
        self.layout.addWidget(self.browse_button)
        
        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.layout.addWidget(self.progress_bar)
        
        # Status Unduhan
        self.status_label = QLabel("Status: Menunggu...")
        self.layout.addWidget(self.status_label)
        
        # Tombol Download
        self.download_button = QPushButton("Download")
        self.download_button.clicked.connect(self.start_download)
        self.layout.addWidget(self.download_button)
        
        # Downloader
        self.downloader = Downloader(self.progress_bar, self.show_completion_notification)

    def choose_directory(self):
        """Menampilkan dialog untuk memilih direktori penyimpanan."""
        directory = QFileDialog.getExistingDirectory(self, "Pilih Direktori Penyimpanan")
        if directory:
            self.directory_path.setText(directory)
            Config.save_last_directory(directory)  # Simpan direktori terakhir

    def get_video_info(self):
        """Dapatkan informasi video dan perbarui GUI."""
        url = self.url_input.text()
        
        if not is_valid_url(url):
            self.video_info.setText("URL tidak valid! Masukkan URL YouTube yang benar.")
            return

        info = self.downloader.get_video_info(url)
        
        if info:
            title = info.get("title", "Tidak tersedia")
            duration = info.get("duration", "Tidak tersedia")
            subtitles = info.get("subtitles", [])
            
            self.video_info.setText(f"Judul: {title}\nDurasi: {duration} detik")
            self.subtitle_language_dropdown.clear()
            self.subtitle_language_dropdown.addItems(subtitles)
        else:
            self.video_info.setText("Gagal mendapatkan informasi video.")

    def start_download(self):
        """Memulai unduhan berdasarkan parameter dari GUI."""
        url = self.url_input.text()
        format_map = {
            "Otomatis": None,
            "Video (MP4)": "video_mp4",
            "Video (WebM)": "video_webm",
            "Audio (MP3)": "audio_mp3",
            "Audio (AAC)": "audio_aac"
        }
        selected_format = format_map[self.format_dropdown.currentText()]
        include_subtitles = self.subtitle_checkbox.isChecked()
        subtitle_language = self.subtitle_language_dropdown.currentText() if include_subtitles else None
        subtitle_format = self.subtitle_format_dropdown.currentText()
        include_thumbnail = self.thumbnail_checkbox.isChecked()
        thumbnail_format = self.thumbnail_format_dropdown.currentText()
        output_directory = self.directory_path.text()
        
        if not is_valid_url(url):
            self.status_label.setText("Status: URL tidak valid.")
            return
        
        if not output_directory:
            self.status_label.setText("Status: Direktori belum dipilih.")
            return
        
        self.status_label.setText("Status: Mulai unduhan...")
        self.downloader.download(
            url,
            selected_format,
            include_subtitles,
            subtitle_language,
            subtitle_format,
            include_thumbnail,
            thumbnail_format,
            output_directory
        )
        self.status_label.setText("Status: Selesai!")

    def show_completion_notification(self):
        """Tampilkan notifikasi bahwa unduhan selesai."""
        QMessageBox.information(self, "Unduhan Selesai", "File berhasil diunduh!")
        self.status_label.setText("Status: Selesai!")
