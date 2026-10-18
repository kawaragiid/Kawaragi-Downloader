import json
import os
import shutil
import sys
import time
import subprocess
import requests
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox, QSpinBox,
    QProgressBar, QMessageBox, QFileDialog, QFrame, QApplication
)
from PyQt5.QtGui import QPixmap, QCursor, QIcon, QImage
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer

from app.core.downloader import Downloader
from app.core.ffmpeg_handler import FFmpegHandler
from app.core.config import Config
from app.utils.validation import is_valid_url
from app.utils.file_utils import get_ffmpeg_path, format_bytes, format_seconds
from app.utils.log_utils import setup_logger
from app.gui.widgets import ScreenshotPreviewDialog, HistoryDialog

logger = setup_logger("main_window", "app.log")

current_task = {"url": None}
received_cookies_cache = {"current": ""}

def get_asset_path(filename):
    """Mendapatkan path asset dengan aman baik saat running script atau pyinstaller."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, "assets", filename)

# --- SERVER LOKAL UNTUK JEMBATAN EKSTENSI ---
class BridgeHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == '/get-task':
            for _ in range(40): 
                if current_task.get("url"):
                    break
                time.sleep(0.5)
                
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(current_task).encode())
            current_task["url"] = None
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == '/submit-cookies':
            content_len = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_len)
            try:
                data = json.loads(post_data.decode('utf-8'))
                received_cookies_cache["current"] = data.get('cookies', "")
            except Exception as e:
                logger.error(f"Error parsing cookies POST: {e}")
                
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.end_headers()
            if hasattr(self.server, 'gui_signal'):
                self.server.gui_signal.emit()
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

class BridgeServer(QThread):
    cookies_ready_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.httpd = None

    def run(self):
        server_address = ('127.0.0.1', 65432)
        try:
            class ReusableServer(ThreadingHTTPServer):
                allow_reuse_address = True
            
            self.httpd = ReusableServer(server_address, BridgeHandler)
            self.httpd.gui_signal = self.cookies_ready_signal
            logger.info("BridgeServer aktif di port 65432")
            self.httpd.serve_forever()
        except OSError as e:
            logger.warning(f"Port 65432 mungkin sedang digunakan oleh sesi lain: {e}")
        except Exception as e:
            logger.error(f"Gagal menjalankan BridgeServer: {e}")

    def stop(self):
        if self.httpd:
            try:
                self.httpd.shutdown()
                self.httpd.server_close()
            except Exception:
                pass


# --- THREAD WORKERS ---
class InfoWorker(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, url, cookies):
        super().__init__()
        self.url = url
        self.cookies = cookies

    def run(self):
        d = Downloader(error_callback=lambda e: self.error.emit(e))
        info = d.get_video_info(self.url, self.cookies)
        if info:
            # Ambil thumbnail bytes jika ada
            thumb_url = info.get("thumbnail")
            if thumb_url:
                try:
                    resp = requests.get(thumb_url, timeout=5)
                    if resp.status_code == 200:
                        info["thumbnail_bytes"] = resp.content
                except Exception:
                    pass
            self.finished.emit(info)
        else:
            self.error.emit("Gagal mengambil informasi video. Periksa link atau koneksi internet.")

class DownloadWorker(QThread):
    progress = pyqtSignal(dict)
    done = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, params):
        super().__init__()
        self.p = params
        self.downloader = None

    def run(self):
        self.downloader = Downloader(
            progress_callback=self.progress.emit,
            completion_callback=self.done.emit,
            error_callback=self.error.emit
        )
        self.downloader.download(
            url=self.p['url'],
            quality=self.p['quality'],
            include_subtitles=self.p['inc_sub'],
            subtitle_language=self.p['sub_lang'],
            subtitle_format=self.p['sub_fmt'],
            include_thumbnail=self.p['inc_thm'],
            thumbnail_format=self.p['thm_fmt'],
            out_dir=self.p['out_dir'],
            browser_cookie=self.p['cookies_data'],
            target_format=self.p['target_fmt']
        )

    def cancel(self):
        if self.downloader:
            self.downloader.cancel()

class ProcessingWorker(QThread):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, mode, input_file, **kwargs):
        super().__init__()
        self.mode = mode
        self.input_file = input_file
        self.kwargs = kwargs

    def run(self):
        try:
            handler = FFmpegHandler()
            if self.mode == "convert":
                res = handler.convert(self.input_file, self.kwargs['ext'])
                self.finished.emit(res)
            elif self.mode == "screenshot":
                res = handler.take_random_screenshots(
                    self.input_file, 
                    self.kwargs['count'], 
                    self.kwargs['duration'], 
                    self.kwargs['dir']
                )
                self.finished.emit(res)
        except Exception as e:
            self.error.emit(str(e))


# --- JENDELA UTAMA (MAIN WINDOW) ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Kawaragi Downloader 🚀")
        self.resize(900, 880)
        self.setMinimumSize(800, 750)

        logo_ico = get_asset_path("logo.ico")
        logo_png = get_asset_path("logo.png")
        self.final_logo = logo_ico if os.path.exists(logo_ico) else logo_png
        self.setWindowIcon(QIcon(self.final_logo))

        self.cookie_file = "Tanpa Login"
        self.current_video_info = {}
        self.current_video_duration = 0
        self.temp_video_file = None
        self.is_downloading = False
        self.is_checking_info = False

        # Timer untuk trigger ekstensi
        self.loading_step = 0
        self.loading_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.loading_timer = QTimer(self)
        self.loading_timer.timeout.connect(self.animate_loading)
        self.trigger_timeout_counter = 0

        # Start bridge server
        self.bridge_server = BridgeServer()
        self.bridge_server.cookies_ready_signal.connect(self.on_cookies_received)
        self.bridge_server.start()

        self.apply_modern_theme()
        self.setup_ui()

    def setup_ui(self):
        self.central_widget = QWidget()
        self.central_widget.setObjectName("central_widget")
        self.setCentralWidget(self.central_widget)

        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(25, 20, 25, 20)
        self.main_layout.setSpacing(12)

        # 1. Header (Logo, Judul, Tombol Riwayat)
        header = QHBoxLayout()
        logo_label = QLabel()
        pix = QPixmap(self.final_logo)
        if not pix.isNull():
            logo_label.setPixmap(pix)
            logo_label.setFixedSize(48, 48)
            logo_label.setScaledContents(True)
        header.addWidget(logo_label)

        title_vbox = QVBoxLayout()
        title = QLabel("Kawaragi Downloader")
        title.setObjectName("app_title")
        subtitle = QLabel("Universal Video Downloader & Post-Processor")
        subtitle.setStyleSheet("color: #7982a9; font-size: 11px;")
        title_vbox.addWidget(title)
        title_vbox.addWidget(subtitle)
        header.addLayout(title_vbox)

        header.addStretch()

        btn_history = QPushButton("📁 Riwayat Unduhan")
        btn_history.setCursor(QCursor(Qt.PointingHandCursor))
        btn_history.setStyleSheet("background-color: #24283b; color: #7aa2f7; border: 1px solid #414868; padding: 8px 16px;")
        btn_history.clicked.connect(self.open_history)
        header.addWidget(btn_history)

        self.main_layout.addLayout(header)

        # 2. Input Link Video & Tempel
        input_label = QLabel("🔗 Tempel Link Video (YouTube, TikTok, Twitter/X, Instagram, dll):")
        input_label.setStyleSheet("font-weight: bold; color: #c0caf5;")
        self.main_layout.addWidget(input_label)

        url_row = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://www.youtube.com/watch?v=...")
        self.url_input.setClearButtonEnabled(True)
        url_row.addWidget(self.url_input)

        self.btn_paste = QPushButton("📋 Tempel")
        self.btn_paste.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_paste.setToolTip("Tempel URL dari clipboard")
        self.btn_paste.clicked.connect(self.paste_from_clipboard)
        url_row.addWidget(self.btn_paste)

        self.main_layout.addLayout(url_row)

        # Action Buttons Row
        action_btn_row = QHBoxLayout()
        self.info_btn = QPushButton("🔍 Cek Info Link")
        self.info_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.info_btn.setStyleSheet("background-color: #3d59a1; color: white; font-weight: bold;")
        self.info_btn.clicked.connect(lambda: self.start_info_check(use_extension=False))
        action_btn_row.addWidget(self.info_btn)

        self.trigger_btn = QPushButton("🛡️ Trigger Ekstensi (Anti-Blokir)")
        self.trigger_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.trigger_btn.setToolTip("Gunakan jika video terkena pembatasan usia atau verifikasi bot")
        self.trigger_btn.setStyleSheet("background-color: #bb9af7; color: #1a1b26; font-weight: bold;")
        self.trigger_btn.clicked.connect(lambda: self.start_info_check(use_extension=True))
        action_btn_row.addWidget(self.trigger_btn)

        self.btn_cancel_action = QPushButton("⏹ Batal")
        self.btn_cancel_action.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_cancel_action.setStyleSheet("background-color: #f7768e; color: white;")
        self.btn_cancel_action.setEnabled(False)
        self.btn_cancel_action.clicked.connect(self.cancel_current_operation)
        action_btn_row.addWidget(self.btn_cancel_action)

        self.main_layout.addLayout(action_btn_row)

        # 3. Card Preview Video Info
        self.preview_frame = QFrame()
        self.preview_frame.setObjectName("preview_frame")
        preview_layout = QHBoxLayout(self.preview_frame)
        preview_layout.setContentsMargins(12, 10, 12, 10)
        preview_layout.setSpacing(15)

        self.thumb_preview = QLabel()
        self.thumb_preview.setFixedSize(140, 80)
        self.thumb_preview.setStyleSheet("background-color: #1a1b26; border-radius: 6px; border: 1px dashed #414868;")
        self.thumb_preview.setAlignment(Qt.AlignCenter)
        self.thumb_preview.setText("🖼️ Thumbnail")
        preview_layout.addWidget(self.thumb_preview)

        self.info_box = QLabel("Menunggu input link... Masukkan URL video di atas dan klik 'Cek Info Link'.")
        self.info_box.setObjectName("info_box")
        self.info_box.setWordWrap(True)
        preview_layout.addWidget(self.info_box, 1)

        self.main_layout.addWidget(self.preview_frame)

        # 4. Pengaturan Kualitas & Format Unduhan
        opt_group = QFrame()
        opt_group.setObjectName("opt_group")
        opt_layout = QVBoxLayout(opt_group)
        opt_layout.setContentsMargins(12, 12, 12, 12)
        opt_layout.setSpacing(10)

        row_settings_1 = QHBoxLayout()
        # Kualitas Video / Audio
        v_qual = QVBoxLayout()
        v_qual.addWidget(QLabel("🎯 Kualitas / Mode Unduh:"))
        self.qual_drop = QComboBox()
        self.qual_drop.addItem("🌟 Kualitas Terbaik (Best / Resolusi Tertinggi)", "best")
        self.qual_drop.addItem("🎬 1080p (Full HD)", "1080p")
        self.qual_drop.addItem("📺 720p (HD)", "720p")
        self.qual_drop.addItem("📱 480p (SD)", "480p")
        self.qual_drop.addItem("⚡ 360p (Hemat Kuota)", "360p")
        self.qual_drop.addItem("🎵 Audio Saja (MP3 320kbps - Kualitas Tinggi)", "audio_320")
        self.qual_drop.addItem("🎵 Audio Saja (MP3 192kbps - Standar)", "audio_192")
        self.qual_drop.addItem("🎵 Audio Saja (M4A / AAC Bawaan)", "audio_m4a")
        v_qual.addWidget(self.qual_drop)
        row_settings_1.addLayout(v_qual)

        # Format Kontainer Tujuan (Remux / Convert)
        v_fmt = QVBoxLayout()
        v_fmt.addWidget(QLabel("📦 Format Tujuan Akhir:"))
        self.fmt_drop = QComboBox()
        self.fmt_drop.addItems(["Otomatis (Sesuai Sumber)", "mp4", "mkv", "webm", "mp3", "aac"])
        v_fmt.addWidget(self.fmt_drop)
        row_settings_1.addLayout(v_fmt)

        opt_layout.addLayout(row_settings_1)

        # Baris Opsi Ekstraksi (Screenshot, Subtitle, Thumbnail)
        row_settings_2 = QHBoxLayout()

        # Screenshot Box
        s_box = QFrame()
        s_box.setStyleSheet("background-color: #1f2335; border-radius: 6px; padding: 6px;")
        s_v = QVBoxLayout(s_box)
        self.ss_cb = QCheckBox("📸 Ambil Screenshot Acak")
        s_v.addWidget(self.ss_cb)
        hbox_ss = QHBoxLayout()
        hbox_ss.addWidget(QLabel("Jumlah:"))
        self.ss_count = QSpinBox()
        self.ss_count.setRange(1, 30)
        self.ss_count.setValue(6)
        hbox_ss.addWidget(self.ss_count)
        hbox_ss.addStretch()
        s_v.addLayout(hbox_ss)
        row_settings_2.addWidget(s_box)

        # Subtitle Box
        sub_box = QFrame()
        sub_box.setStyleSheet("background-color: #1f2335; border-radius: 6px; padding: 6px;")
        sub_v = QVBoxLayout(sub_box)
        self.sub_cb = QCheckBox("📝 Unduh Subtitle")
        sub_v.addWidget(self.sub_cb)
        sub_row = QHBoxLayout()
        self.sub_lang = QComboBox()
        self.sub_lang.setPlaceholderText("Pilih Bahasa")
        self.sub_lang.addItem("en")
        self.sub_lang.addItem("id")
        sub_row.addWidget(self.sub_lang)
        self.sub_fmt = QComboBox()
        self.sub_fmt.addItems(["srt", "vtt", "ass"])
        sub_row.addWidget(self.sub_fmt)
        sub_v.addLayout(sub_row)
        row_settings_2.addWidget(sub_box)

        # Thumbnail Box
        thm_box = QFrame()
        thm_box.setStyleSheet("background-color: #1f2335; border-radius: 6px; padding: 6px;")
        thm_v = QVBoxLayout(thm_box)
        self.thm_cb = QCheckBox("🖼️ Simpan Thumbnail")
        thm_v.addWidget(self.thm_cb)
        thm_row = QHBoxLayout()
        thm_row.addWidget(QLabel("Format:"))
        self.thm_fmt = QComboBox()
        self.thm_fmt.addItems(["jpg", "png", "webp"])
        thm_row.addWidget(self.thm_fmt)
        thm_v.addLayout(thm_row)
        row_settings_2.addWidget(thm_box)

        opt_layout.addLayout(row_settings_2)
        self.main_layout.addWidget(opt_group)

        # 5. Folder Tujuan Simpan
        dir_label = QLabel("📂 Simpan Berkas ke:")
        dir_label.setStyleSheet("color: #c0caf5; font-weight: bold;")
        self.main_layout.addWidget(dir_label)

        dir_h = QHBoxLayout()
        self.dir_in = QLineEdit()
        self.dir_in.setText(Config.load_last_directory())
        dir_h.addWidget(self.dir_in)

        btn_browse = QPushButton("Ganti Folder")
        btn_browse.setCursor(QCursor(Qt.PointingHandCursor))
        btn_browse.clicked.connect(self.browse_folder)
        dir_h.addWidget(btn_browse)

        btn_open_dir = QPushButton("Buka Folder")
        btn_open_dir.setCursor(QCursor(Qt.PointingHandCursor))
        btn_open_dir.setStyleSheet("background-color: #24283b; border: 1px solid #414868; color: #7aa2f7;")
        btn_open_dir.clicked.connect(self.open_current_directory)
        dir_h.addWidget(btn_open_dir)

        self.main_layout.addLayout(dir_h)

        # 6. Status & Progress Bar
        self.main_layout.addStretch()

        self.status = QLabel("Status: Siap")
        self.status.setStyleSheet("font-weight: bold; color: #7aa2f7; font-size: 13px;")
        self.main_layout.addWidget(self.status)

        self.detail_stats = QLabel("Kecepatan: -- | Sisa Waktu: -- | Ukuran: --")
        self.detail_stats.setStyleSheet("color: #7982a9; font-size: 12px;")
        self.main_layout.addWidget(self.detail_stats)

        self.p_bar = QProgressBar()
        self.p_bar.setValue(0)
        self.main_layout.addWidget(self.p_bar)

        # 7. Tombol Eksekusi Utama
        btn_action_row = QHBoxLayout()
        self.dl_btn = QPushButton("🚀 MULAI UNDUH SEKARANG")
        self.dl_btn.setObjectName("download_btn")
        self.dl_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.dl_btn.clicked.connect(self.run_dl)
        btn_action_row.addWidget(self.dl_btn, 4)

        self.main_layout.addLayout(btn_action_row)

    def paste_from_clipboard(self):
        clipboard = QApplication.clipboard()
        text = clipboard.text().strip()
        if text:
            self.url_input.setText(text)
            if is_valid_url(text):
                # Auto cek info jika URL valid
                self.start_info_check(use_extension=False)
        else:
            QMessageBox.information(self, "Clipboard Kosong", "Tidak ada teks yang dapat disalin dari clipboard.")

    def browse_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Pilih Folder Penyimpanan")
        if d:
            self.dir_in.setText(d)
            Config.save_last_directory(d)

    def open_current_directory(self):
        d = self.dir_in.text()
        if os.path.exists(d):
            os.startfile(d)
        else:
            QMessageBox.warning(self, "Folder Tidak Ditemukan", f"Folder tidak ada:\n{d}")

    def open_history(self):
        dialog = HistoryDialog(self)
        dialog.exec_()

    def start_info_check(self, use_extension=False):
        url = self.url_input.text().strip()
        if not is_valid_url(url):
            QMessageBox.warning(self, "URL Tidak Valid", "Silakan masukkan tautan video yang benar (contoh: https://...)")
            return

        self.is_checking_info = True
        self.info_btn.setEnabled(False)
        self.trigger_btn.setEnabled(False)
        self.btn_cancel_action.setEnabled(True)

        if use_extension:
            self.trigger_timeout_counter = 0
            received_cookies_cache["current"] = ""
            current_task["url"] = url
            self.status.setText("Status: Menghubungi ekstensi Chrome...")
            self.loading_timer.start(100)
        else:
            self.status.setText("Status: Mengambil informasi video...")
            self.cookie_file = "Tanpa Login"
            self.launch_info_worker(url, self.cookie_file)

    def launch_info_worker(self, url, cookie_file):
        self.info_worker = InfoWorker(url, cookie_file)
        self.info_worker.finished.connect(self.on_info_ok)
        self.info_worker.error.connect(self.on_error)
        self.info_worker.start()

    def on_cookies_received(self):
        self.loading_timer.stop()
        self.status.setText("Status: Kunci cookies berhasil disinkronkan!")
        cookies_text = received_cookies_cache["current"]

        app_data_dir = Config.get_app_data_dir()
        self.cookie_file = os.path.join(app_data_dir, "temp_cookies.txt") if cookies_text else "Tanpa Login"

        if cookies_text:
            try:
                with open(self.cookie_file, "w", encoding="utf-8") as f:
                    f.write(cookies_text)
            except Exception as e:
                logger.error(f"Gagal menulis cookie_file: {e}")

        self.launch_info_worker(self.url_input.text().strip(), self.cookie_file)

    def animate_loading(self):
        frame = self.loading_frames[self.loading_step % len(self.loading_frames)]
        self.loading_step += 1
        self.trigger_timeout_counter += 1

        seconds_elapsed = self.trigger_timeout_counter // 10
        self.info_box.setText(
            f"<p align='center'><span style='font-size:24px; color:#bb9af7;'>{frame}</span><br>"
            f"<b>Menghubungi Ekstensi Chrome... ({seconds_elapsed}s)</b><br>"
            f"<span style='font-size:11px; color:#7982a9;'>Jika ekstensi belum terpasang, proses akan otomatis berlanjut tanpa login.</span></p>"
        )

        # Timeout 6 detik: jika ekstensi tidak merespons, fallback ke download langsung!
        if self.trigger_timeout_counter >= 60:
            self.loading_timer.stop()
            self.status.setText("Status: Ekstensi tidak terdeteksi, melanjutkan tanpa login.")
            self.cookie_file = "Tanpa Login"
            self.launch_info_worker(self.url_input.text().strip(), self.cookie_file)

    def on_info_ok(self, info):
        self.loading_timer.stop()
        self.is_checking_info = False
        self.info_btn.setEnabled(True)
        self.trigger_btn.setEnabled(True)
        self.btn_cancel_action.setEnabled(False)

        self.current_video_info = info
        self.current_video_duration = info.get('duration', 0)
        dur_str = format_seconds(self.current_video_duration)
        uploader = info.get('uploader', 'Tidak diketahui')
        title = info.get('title', 'Tidak ada judul')

        # Tampilkan Thumbnail
        if "thumbnail_bytes" in info and info["thumbnail_bytes"]:
            pixmap = QPixmap()
            pixmap.loadFromData(info["thumbnail_bytes"])
            if not pixmap.isNull():
                self.thumb_preview.setPixmap(
                    pixmap.scaled(self.thumb_preview.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                )
        else:
            self.thumb_preview.setText("🎬 Video")

        self.info_box.setText(
            f"<b>{title}</b><br>"
            f"<span style='color:#7aa2f7;'>Channel:</span> {uploader} &nbsp;|&nbsp; "
            f"<span style='color:#7aa2f7;'>Durasi:</span> {dur_str} ({self.current_video_duration}s)"
        )

        # Perbarui dropdown subtitle
        subs = info.get('subtitles', [])
        if subs:
            self.sub_lang.clear()
            self.sub_lang.addItems(subs)
            self.sub_cb.setEnabled(True)
        else:
            self.sub_lang.clear()
            self.sub_lang.addItem("Tidak ada")

        self.status.setText("Status: Informasi video siap diunduh!")

    def run_dl(self):
        url = self.url_input.text().strip()
        if not is_valid_url(url):
            QMessageBox.warning(self, "URL Kosong", "Masukkan tautan video terlebih dahulu!")
            return

        out_dir = self.dir_in.text().strip()
        if not out_dir:
            out_dir = Config.load_last_directory()
            self.dir_in.setText(out_dir)

        self.is_downloading = True
        self.dl_btn.setEnabled(False)
        self.info_btn.setEnabled(False)
        self.trigger_btn.setEnabled(False)
        self.btn_cancel_action.setEnabled(True)

        self.status.setText("Status: Mempersiapkan unduhan...")
        self.detail_stats.setText("Memulai koneksi...")
        self.p_bar.setValue(0)

        quality_val = self.qual_drop.currentData() or "best"
        target_fmt = self.fmt_drop.currentText()

        p = {
            'url': url,
            'out_dir': out_dir,
            'quality': quality_val,
            'cookies_data': getattr(self, 'cookie_file', "Tanpa Login"),
            'inc_sub': self.sub_cb.isChecked(),
            'sub_lang': self.sub_lang.currentText(),
            'sub_fmt': self.sub_fmt.currentText(),
            'inc_thm': self.thm_cb.isChecked(),
            'thm_fmt': self.thm_fmt.currentText(),
            'target_fmt': target_fmt
        }

        self.download_worker = DownloadWorker(p)
        self.download_worker.progress.connect(self.on_download_progress)
        self.download_worker.done.connect(self.on_dl_done)
        self.download_worker.error.connect(self.on_error)
        self.download_worker.start()

    def on_download_progress(self, data):
        if isinstance(data, dict):
            percent = data.get("percent", 0)
            self.p_bar.setValue(percent)
            speed = data.get("speed", "--")
            eta = data.get("eta", "--")
            downloaded = data.get("downloaded", "--")
            total = data.get("total", "--")
            status_text = data.get("status", "Mengunduh...")
            
            self.status.setText(f"Status: {status_text}")
            self.detail_stats.setText(f"Kecepatan: {speed}  |  Sisa Waktu: {eta}  |  Ukuran: {downloaded} / {total}")
        elif isinstance(data, int):
            self.p_bar.setValue(data)

    def on_dl_done(self, file_path):
        self.temp_video_file = file_path
        
        # Simpan ke riwayat unduhan
        title = self.current_video_info.get("title") or os.path.basename(file_path)
        Config.save_history_entry({
            "title": title,
            "url": self.url_input.text().strip(),
            "file_path": file_path,
            "duration": self.current_video_duration,
            "format": self.fmt_drop.currentText()
        })

        # Alur Screenshot jika dicentang
        if self.ss_cb.isChecked() and self.current_video_duration > 0:
            self.status.setText("Status: Mengambil cuplikan screenshot acak...")
            self.proc = ProcessingWorker(
                "screenshot", 
                file_path, 
                count=self.ss_count.value(), 
                duration=self.current_video_duration, 
                dir=self.dir_in.text()
            )
            self.proc.finished.connect(self.show_ss_preview)
            self.proc.error.connect(self.on_error)
            self.proc.start()
        else:
            self.handle_conversion(file_path)

    def show_ss_preview(self, shot_paths):
        if not shot_paths:
            self.handle_conversion(self.temp_video_file)
            return

        dialog = ScreenshotPreviewDialog(shot_paths, self)
        result = dialog.exec_()

        main_dir = self.dir_in.text()
        if result == ScreenshotPreviewDialog.Accepted:
            selected_files = dialog.get_selected_files()
            saved_count = 0
            for path in shot_paths:
                if path in selected_files:
                    filename = os.path.basename(path)
                    new_path = os.path.join(main_dir, f"kawaragi_{filename}")
                    try:
                        shutil.move(path, new_path)
                        saved_count += 1
                    except Exception:
                        pass
                else:
                    try:
                        os.remove(path)
                    except Exception:
                        pass
            self.status.setText(f"Status: {saved_count} gambar screenshot disimpan.")
        else:
            for path in shot_paths:
                try:
                    os.remove(path)
                except Exception:
                    pass
            self.status.setText("Status: Seluruh screenshot dibatalkan.")

        # Bersihkan folder temp screenshot
        temp_dir = os.path.dirname(shot_paths[0])
        if os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass

        self.handle_conversion(self.temp_video_file)

    def handle_conversion(self, file_path):
        target = self.fmt_drop.currentText()
        if target != "Otomatis (Sesuai Sumber)":
            actual_ext = os.path.splitext(file_path)[1].replace(".", "").lower()
            if actual_ext != target.lower():
                self.status.setText(f"Status: Merender otomatis ke {target} via FFmpeg...")
                self.proc = ProcessingWorker("convert", file_path, ext=target)
                self.proc.finished.connect(self.final_step)
                self.proc.error.connect(self.on_error)
                self.proc.start()
                return

        self.final_step(file_path)

    def final_step(self, final_file_path):
        self.is_downloading = False
        self.dl_btn.setEnabled(True)
        self.info_btn.setEnabled(True)
        self.trigger_btn.setEnabled(True)
        self.btn_cancel_action.setEnabled(False)

        self.status.setText("Status: Selesai! Berkas siap digunakan.")
        self.detail_stats.setText("Unduhan berhasil diselesaikan.")
        self.p_bar.setValue(100)

        # Dialog sukses dengan tombol aksi langsung
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Unduhan Berhasil 🎉")
        msg_box.setText(f"<b>Proses Selesai!</b><br><br>Berkas disimpan di:<br><code>{final_file_path}</code>")
        msg_box.setIcon(QMessageBox.Information)
        
        btn_play = msg_box.addButton("▶ Putar Berkas", QMessageBox.ActionRole)
        btn_folder = msg_box.addButton("📁 Buka Folder", QMessageBox.ActionRole)
        msg_box.addButton("Tutup", QMessageBox.RejectRole)
        
        msg_box.exec_()
        
        clicked = msg_box.clickedButton()
        if clicked == btn_play:
            if os.path.exists(final_file_path):
                os.startfile(final_file_path)
        elif clicked == btn_folder:
            folder = os.path.dirname(final_file_path)
            if os.path.exists(folder):
                subprocess.run(f'explorer /select,"{os.path.normpath(final_file_path)}"', shell=True)

    def cancel_current_operation(self):
        if self.is_checking_info:
            self.loading_timer.stop()
            self.is_checking_info = False
            self.info_btn.setEnabled(True)
            self.trigger_btn.setEnabled(True)
            self.btn_cancel_action.setEnabled(False)
            self.status.setText("Status: Pemeriksaan info dibatalkan.")
            self.info_box.setText("Pemeriksaan tautan dibatalkan.")

        if self.is_downloading and hasattr(self, 'download_worker'):
            self.status.setText("Status: Membatalkan unduhan...")
            self.download_worker.cancel()

    def on_error(self, msg):
        self.loading_timer.stop()
        self.is_checking_info = False
        self.is_downloading = False
        self.info_btn.setEnabled(True)
        self.trigger_btn.setEnabled(True)
        self.dl_btn.setEnabled(True)
        self.btn_cancel_action.setEnabled(False)

        self.status.setText("Status: Gagal.")
        self.detail_stats.setText("Terjadi kesalahan pada proses.")
        self.info_box.setText(f"<span style='color:#f7768e;'>❌ {msg}</span>")

    def apply_modern_theme(self):
        self.setStyleSheet("""
            QMainWindow, QWidget#central_widget { 
                background-color: #1a1b26; 
            }
            QLabel { 
                color: #a9b1d6; 
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
                font-size: 13px; 
            }
            QLabel#app_title { 
                color: #7aa2f7; 
                font-size: 22px; 
                font-weight: bold; 
            }
            QFrame#preview_frame {
                background-color: #24283b;
                border: 1px solid #414868;
                border-radius: 8px;
            }
            QFrame#opt_group {
                background-color: #24283b;
                border: 1px solid #414868;
                border-radius: 8px;
            }
            QLabel#info_box { 
                color: #c0caf5; 
                font-size: 13px;
            }
            QLineEdit, QComboBox, QSpinBox { 
                background-color: #1f2335; 
                color: #c0caf5; 
                border: 1px solid #414868; 
                border-radius: 6px; 
                padding: 7px 10px; 
                font-size: 13px;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
                border: 1px solid #7aa2f7;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QPushButton { 
                background-color: #3d59a1; 
                color: white; 
                border-radius: 6px; 
                padding: 9px 16px; 
                font-weight: bold; 
                font-size: 13px;
                border: none;
            }
            QPushButton:hover {
                opacity: 0.9;
                background-color: #4869bd;
            }
            QPushButton:disabled {
                background-color: #2e3440;
                color: #565f89;
            }
            QPushButton#download_btn { 
                background-color: #9ece6a; 
                color: #1a1b26; 
                font-size: 15px; 
                padding: 12px; 
                font-weight: bold;
            }
            QPushButton#download_btn:hover { 
                background-color: #a9db76; 
            }
            QProgressBar { 
                border: 1px solid #414868; 
                border-radius: 8px; 
                background-color: #1f2335; 
                text-align: center; 
                color: white; 
                font-weight: bold;
                height: 20px;
            }
            QProgressBar::chunk { 
                background-color: #7aa2f7; 
                border-radius: 7px; 
            }
            QCheckBox { 
                color: #c0caf5; 
                font-size: 13px; 
                spacing: 8px;
            }
            QCheckBox::indicator { 
                width: 18px; 
                height: 18px; 
                border-radius: 4px;
                border: 1px solid #414868;
                background-color: #1f2335;
            }
            QCheckBox::indicator:checked {
                background-color: #7aa2f7;
                border-color: #7aa2f7;
            }
            QToolTip {
                background-color: #24283b;
                color: #c0caf5;
                border: 1px solid #414868;
                padding: 4px;
            }
        """)

    def closeEvent(self, event):
        # Stop background bridge server cleanly
        if hasattr(self, 'bridge_server') and self.bridge_server:
            self.bridge_server.stop()

        # Bersihkan file temporary cookie dari AppData
        cookie_path = os.path.join(Config.get_app_data_dir(), 'temp_cookies.txt')
        if os.path.exists(cookie_path):
            try:
                os.remove(cookie_path)
            except Exception:
                pass

        event.accept()