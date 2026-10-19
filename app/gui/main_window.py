import json
import os
import shutil
import sys
import time
import html
import subprocess
import traceback
import requests
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox, QSpinBox,
    QProgressBar, QMessageBox, QFileDialog, QFrame, QApplication,
    QTextEdit
)
from PyQt5.QtGui import QPixmap, QCursor, QIcon, QTextCursor
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer

from app.core.downloader import Downloader
from app.core.ffmpeg_handler import FFmpegHandler
from app.core.config import Config
from app.utils.validation import is_valid_url
from app.utils.file_utils import get_ffmpeg_path, get_extension_dir, format_bytes, format_seconds
from app.utils.log_utils import setup_logger
from app.gui.widgets import ScreenshotPreviewDialog, HistoryDialog, ExtensionHelperDialog

logger = setup_logger("main_window", "app.log")

current_task = {"url": None}
received_cookies_cache = {
    "current": "",
    "count": 0,
    "userAgent": "",
    "tab_url": "",
    "tab_title": ""
}
bridge_state = {"last_seen": 0.0}


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

    def handle(self):
        """Tangkap pemutusan koneksi sepihak oleh klien browser agar tidak membuang traceback ke terminal."""
        try:
            super().handle()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass

    def _send_json(self, payload: dict, status_code: int = 200):
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode('utf-8'))

    def do_GET(self):
        try:
            bridge_state["last_seen"] = time.time()
            if hasattr(self.server, 'ext_connected_signal'):
                self.server.ext_connected_signal.emit(True)

            if self.path == '/ping':
                self._send_json({"status": "ready", "app": "Kawaragi Downloader"})
            elif self.path == '/get-task':
                # Tunggu maks 4 detik agar ekstensi tetap responsif dan tidak terkena suspend Chrome
                for _ in range(8):
                    if current_task.get("url"):
                        break
                    time.sleep(0.5)

                bridge_state["last_seen"] = time.time()
                task_payload = {"url": current_task.get("url")}
                current_task["url"] = None
                self._send_json(task_payload)
            else:
                self._send_json({"error": "Not found"}, 404)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass

    def do_POST(self):
        try:
            bridge_state["last_seen"] = time.time()
            if hasattr(self.server, 'ext_connected_signal'):
                self.server.ext_connected_signal.emit(True)

            content_len = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_len) if content_len > 0 else b"{}"
            try:
                data = json.loads(post_data.decode('utf-8'))
            except Exception as e:
                logger.error(f"Error parsing JSON POST: {e}")
                data = {}

            if self.path == '/submit-cookies':
                received_cookies_cache["current"] = data.get('cookies', "")
                received_cookies_cache["count"] = data.get('count', 0)
                received_cookies_cache["userAgent"] = data.get('userAgent', "")
                self._send_json({"status": "ok"})
                if hasattr(self.server, 'cookies_ready_signal'):
                    self.server.cookies_ready_signal.emit()

            elif self.path == '/send-tab':
                received_cookies_cache["current"] = data.get('cookies', "")
                received_cookies_cache["count"] = data.get('count', 0)
                received_cookies_cache["userAgent"] = data.get('userAgent', "")
                received_cookies_cache["tab_url"] = data.get('url', "")
                received_cookies_cache["tab_title"] = data.get('title', "")
                self._send_json({"status": "ok"})
                if hasattr(self.server, 'tab_received_signal'):
                    self.server.tab_received_signal.emit()
            else:
                self._send_json({"error": "Not found"}, 404)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass

    def do_OPTIONS(self):
        try:
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.end_headers()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass


class BridgeServer(QThread):
    cookies_ready_signal = pyqtSignal()
    tab_received_signal = pyqtSignal()
    ext_connected_signal = pyqtSignal(bool)
    server_log_signal = pyqtSignal(str, str)

    def __init__(self):
        super().__init__()
        self.httpd = None

    def _cleanup_stale_port_holder(self):
        """Membersihkan proses zombie KawaragiDownloader lama yang masih mengunci port 65432."""
        if os.name != 'nt':
            return
        try:
            flags = subprocess.CREATE_NO_WINDOW
            out = subprocess.check_output(["netstat", "-ano"], creationflags=flags, text=True, errors="ignore")
            my_pid = str(os.getpid())
            for line in out.splitlines():
                if "127.0.0.1:65432" in line and "LISTENING" in line:
                    parts = line.split()
                    if parts:
                        pid = parts[-1]
                        if pid.isdigit() and pid != my_pid and pid != "0":
                            subprocess.run(["taskkill", "/F", "/PID", pid], creationflags=flags, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def run(self):
        self._cleanup_stale_port_holder()
        server_address = ('127.0.0.1', 65432)
        try:
            class ReusableServer(ThreadingHTTPServer):
                allow_reuse_address = True

                def handle_error(self, request, client_address):
                    exc_type, _, _ = sys.exc_info()
                    if exc_type in (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                        return
                    super().handle_error(request, client_address)

            self.httpd = ReusableServer(server_address, BridgeHandler)
            self.httpd.cookies_ready_signal = self.cookies_ready_signal
            self.httpd.tab_received_signal = self.tab_received_signal
            self.httpd.ext_connected_signal = self.ext_connected_signal
            logger.info("BridgeServer aktif di port 65432")
            self.server_log_signal.emit("INFO", "🌐 Bridge Server lokal aktif di 127.0.0.1:65432 (Menunggu koneksi ekstensi browser)")
            self.httpd.serve_forever()
        except OSError as e:
            msg = f"Port 65432 sedang digunakan ({e}). Pastikan tidak ada jendela Kawaragi lain yang terbuka."
            logger.warning(msg)
            self.server_log_signal.emit("WARNING", msg)
        except Exception as e:
            logger.error(f"Gagal menjalankan BridgeServer: {e}")
            self.server_log_signal.emit("ERROR", f"Gagal menjalankan BridgeServer: {e}")

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
    log_msg = pyqtSignal(str, str)

    def __init__(self, url, cookies, user_agent=""):
        super().__init__()
        self.url = url
        self.cookies = cookies
        self.user_agent = user_agent

    def run(self):
        d = Downloader(
            error_callback=lambda e: self.error.emit(e),
            log_callback=lambda lvl, msg: self.log_msg.emit(lvl, msg)
        )
        info = d.get_video_info(self.url, self.cookies, self.user_agent)
        if info:
            thumb_url = info.get("thumbnail")
            if thumb_url:
                try:
                    resp = requests.get(thumb_url, timeout=5, headers={"Referer": self.url, "User-Agent": "Mozilla/5.0"})
                    if resp.status_code == 200:
                        info["thumbnail_bytes"] = resp.content
                except Exception:
                    pass
            self.finished.emit(info)


class DownloadWorker(QThread):
    progress = pyqtSignal(dict)
    done = pyqtSignal(str)
    error = pyqtSignal(str)
    log_msg = pyqtSignal(str, str)

    def __init__(self, params):
        super().__init__()
        self.p = params
        self.downloader = None

    def run(self):
        self.downloader = Downloader(
            progress_callback=self.progress.emit,
            completion_callback=self.done.emit,
            error_callback=self.error.emit,
            log_callback=lambda lvl, msg: self.log_msg.emit(lvl, msg)
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
            target_format=self.p['target_fmt'],
            custom_user_agent=self.p.get('user_agent', '')
        )

    def cancel(self):
        if self.downloader:
            self.downloader.cancel()


class ProcessingWorker(QThread):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)
    log_msg = pyqtSignal(str, str)

    def __init__(self, mode, input_file, **kwargs):
        super().__init__()
        self.mode = mode
        self.input_file = input_file
        self.kwargs = kwargs

    def run(self):
        try:
            handler = FFmpegHandler()
            if self.mode == "convert":
                self.log_msg.emit("INFO", f"🎬 Memulai konversi FFmpeg: {os.path.basename(self.input_file)} -> .{self.kwargs['ext']}")
                res = handler.convert(self.input_file, self.kwargs['ext'])
                self.log_msg.emit("SUCCESS", f"✅ Konversi selesai: {res}")
                self.finished.emit(res)
            elif self.mode == "screenshot":
                self.log_msg.emit("INFO", f"📸 Mengambil {self.kwargs['count']} screenshot acak via FFmpeg...")
                res = handler.take_random_screenshots(
                    self.input_file,
                    self.kwargs['count'],
                    self.kwargs['duration'],
                    self.kwargs['dir']
                )
                self.log_msg.emit("SUCCESS", f"✅ Berhasil mengekstrak {len(res)} gambar screenshot.")
                self.finished.emit(res)
        except Exception as e:
            tb = traceback.format_exc()
            self.log_msg.emit("ERROR", f"❌ Error pemrosesan FFmpeg: {e}\n{tb}")
            self.error.emit(str(e))


# --- JENDELA UTAMA (MAIN WINDOW) ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Kawaragi Downloader 🚀")
        self.resize(960, 940)
        self.setMinimumSize(850, 820)

        logo_ico = get_asset_path("logo.ico")
        logo_png = get_asset_path("logo.png")
        self.final_logo = logo_ico if os.path.exists(logo_ico) else logo_png
        self.setWindowIcon(QIcon(self.final_logo))

        self.cookie_file = "Tanpa Login"
        self.custom_user_agent = ""
        self.manual_cookie_path = ""
        self.current_video_info = {}
        self.current_video_duration = 0
        self.temp_video_file = None
        self.is_downloading = False
        self.is_checking_info = False
        self.extension_connected = False
        self.pending_action_after_cookies = "info"  # "info" atau "download"

        # Timer animasi trigger ekstensi
        self.loading_step = 0
        self.loading_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.loading_timer = QTimer(self)
        self.loading_timer.timeout.connect(self.animate_loading)
        self.trigger_timeout_counter = 0

        # Timer pemantau status ekstensi
        self.ext_watchdog_timer = QTimer(self)
        self.ext_watchdog_timer.timeout.connect(self.check_extension_heartbeat)
        self.ext_watchdog_timer.start(3000)

        self.apply_modern_theme()
        self.setup_ui()

        # Jalankan server jembatan ekstensi
        self.bridge_server = BridgeServer()
        self.bridge_server.cookies_ready_signal.connect(self.on_cookies_received)
        self.bridge_server.tab_received_signal.connect(self.on_tab_received_from_extension)
        self.bridge_server.ext_connected_signal.connect(self.update_extension_badge)
        self.bridge_server.server_log_signal.connect(self.append_log)
        self.bridge_server.start()

        self.append_log("INFO", f"Aplikasi Kawaragi Downloader siap. FFmpeg: {get_ffmpeg_path()}")
        self.append_log("INFO", f"Lokasi folder ekstensi browser: {get_extension_dir()}")

        # Jika dijalankan oleh installer dengan argumen --install-extension, buka panduan otomatis
        if "--install-extension" in sys.argv:
            QTimer.singleShot(600, self.open_extension_helper)

    def setup_ui(self):
        self.central_widget = QWidget()
        self.central_widget.setObjectName("central_widget")
        self.setCentralWidget(self.central_widget)

        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(22, 16, 22, 16)
        self.main_layout.setSpacing(10)

        # 1. Header (Logo, Judul, Indikator Ekstensi, Tombol Pasang Ekstensi & Riwayat)
        header = QHBoxLayout()
        logo_label = QLabel()
        pix = QPixmap(self.final_logo)
        if not pix.isNull():
            logo_label.setPixmap(pix)
            logo_label.setFixedSize(44, 44)
            logo_label.setScaledContents(True)
        header.addWidget(logo_label)

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(2)
        title = QLabel("Kawaragi Downloader")
        title.setObjectName("app_title")
        subtitle = QLabel("Universal Multi-Site Video Downloader & FFmpeg Studio")
        subtitle.setStyleSheet("color: #7982a9; font-size: 11px;")
        title_vbox.addWidget(title)
        title_vbox.addWidget(subtitle)
        header.addLayout(title_vbox)

        header.addStretch()

        self.ext_status_badge = QLabel("🔴 Ekstensi: Belum Terhubung")
        self.ext_status_badge.setStyleSheet(
            "background-color: #24283b; color: #f7768e; border: 1px solid #f7768e; "
            "border-radius: 6px; padding: 6px 10px; font-weight: bold; font-size: 12px;"
        )
        header.addWidget(self.ext_status_badge)

        btn_ext_helper = QPushButton("🧩 Pasang Ekstensi")
        btn_ext_helper.setCursor(QCursor(Qt.PointingHandCursor))
        btn_ext_helper.setStyleSheet("background-color: #bb9af7; color: #1a1b26; padding: 7px 13px; font-weight: bold;")
        btn_ext_helper.clicked.connect(self.open_extension_helper)
        header.addWidget(btn_ext_helper)

        btn_history = QPushButton("📁 Riwayat")
        btn_history.setCursor(QCursor(Qt.PointingHandCursor))
        btn_history.setStyleSheet("background-color: #24283b; color: #7aa2f7; border: 1px solid #414868; padding: 7px 13px;")
        btn_history.clicked.connect(self.open_history)
        header.addWidget(btn_history)

        self.main_layout.addLayout(header)

        # 2. Input Link Video & Tempel
        input_label = QLabel("🔗 Tempel Tautan Video (YouTube, Bilibili, TikTok, Instagram, Twitter/X, Facebook, dll):")
        input_label.setStyleSheet("font-weight: bold; color: #c0caf5;")
        self.main_layout.addWidget(input_label)

        url_row = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://www.youtube.com/watch?v=... atau https://www.bilibili.com/video/...")
        self.url_input.setClearButtonEnabled(True)
        url_row.addWidget(self.url_input)

        self.btn_paste = QPushButton("📋 Tempel & Cek")
        self.btn_paste.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_paste.setToolTip("Tempel URL dari clipboard dan langsung periksa info video")
        self.btn_paste.clicked.connect(self.paste_from_clipboard)
        url_row.addWidget(self.btn_paste)

        self.main_layout.addLayout(url_row)

        # Action Buttons & Sumber Cookies Row
        action_btn_row = QHBoxLayout()

        self.auth_drop = QComboBox()
        self.auth_drop.setToolTip("Pilih metode autentikasi / cookies untuk situs yang membutuhkan login")
        self.auth_drop.addItem("🌐 Autentikasi: Otomatis (Tanpa Login + Fallback)", "Tanpa Login")
        self.auth_drop.addItem("🧩 Autentikasi: Ekstensi Kawaragi Trigger (Browser)", "extension")
        self.auth_drop.addItem("🧭 Autentikasi: Ambil Cookies dari Microsoft Edge", "edge")
        self.auth_drop.addItem("🦊 Autentikasi: Ambil Cookies dari Mozilla Firefox", "firefox")
        self.auth_drop.addItem("🦁 Autentikasi: Ambil Cookies dari Brave Browser", "brave")
        self.auth_drop.addItem("🌐 Autentikasi: Ambil Cookies dari Google Chrome", "chrome")
        self.auth_drop.addItem("📄 Autentikasi: Pilih File cookies.txt Manual...", "file")
        self.auth_drop.currentIndexChanged.connect(self.on_auth_mode_changed)
        action_btn_row.addWidget(self.auth_drop, 2)

        self.info_btn = QPushButton("🔍 Cek Info Link")
        self.info_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.info_btn.setStyleSheet("background-color: #3d59a1; color: white; font-weight: bold;")
        self.info_btn.clicked.connect(lambda: self.start_info_check(force_extension=False))
        action_btn_row.addWidget(self.info_btn, 1)

        self.trigger_btn = QPushButton("🛡️ Sinkron Cookie Ekstensi")
        self.trigger_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.trigger_btn.setToolTip("Tarik cookies aktif dari ekstensi browser Kawaragi Trigger")
        self.trigger_btn.setStyleSheet("background-color: #bb9af7; color: #1a1b26; font-weight: bold;")
        self.trigger_btn.clicked.connect(lambda: self.start_info_check(force_extension=True))
        action_btn_row.addWidget(self.trigger_btn, 1)

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
        preview_layout.setContentsMargins(12, 8, 12, 8)
        preview_layout.setSpacing(14)

        self.thumb_preview = QLabel()
        self.thumb_preview.setFixedSize(135, 76)
        self.thumb_preview.setStyleSheet("background-color: #1a1b26; border-radius: 6px; border: 1px dashed #414868;")
        self.thumb_preview.setAlignment(Qt.AlignCenter)
        self.thumb_preview.setText("🖼️ Thumbnail")
        preview_layout.addWidget(self.thumb_preview)

        self.info_box = QLabel("Menunggu input link... Masukkan URL video di atas lalu klik 'Cek Info Link' atau langsung 'Mulai Unduh'.")
        self.info_box.setObjectName("info_box")
        self.info_box.setWordWrap(True)
        preview_layout.addWidget(self.info_box, 1)

        self.main_layout.addWidget(self.preview_frame)

        # 4. Pengaturan Kualitas & Format Unduhan
        opt_group = QFrame()
        opt_group.setObjectName("opt_group")
        opt_layout = QVBoxLayout(opt_group)
        opt_layout.setContentsMargins(12, 10, 12, 10)
        opt_layout.setSpacing(8)

        row_settings_1 = QHBoxLayout()
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

        v_fmt = QVBoxLayout()
        v_fmt.addWidget(QLabel("📦 Format Tujuan Akhir:"))
        self.fmt_drop = QComboBox()
        self.fmt_drop.addItems(["Otomatis (Sesuai Sumber)", "mp4", "mkv", "webm", "mp3", "aac"])
        v_fmt.addWidget(self.fmt_drop)
        row_settings_1.addLayout(v_fmt)

        opt_layout.addLayout(row_settings_1)

        # Baris Opsi Ekstraksi (Screenshot, Subtitle, Thumbnail)
        row_settings_2 = QHBoxLayout()

        s_box = QFrame()
        s_box.setStyleSheet("background-color: #1f2335; border-radius: 6px; padding: 5px;")
        s_v = QVBoxLayout(s_box)
        s_v.setContentsMargins(6, 4, 6, 4)
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

        sub_box = QFrame()
        sub_box.setStyleSheet("background-color: #1f2335; border-radius: 6px; padding: 5px;")
        sub_v = QVBoxLayout(sub_box)
        sub_v.setContentsMargins(6, 4, 6, 4)
        self.sub_cb = QCheckBox("📝 Unduh Subtitle")
        sub_v.addWidget(self.sub_cb)
        sub_row = QHBoxLayout()
        self.sub_lang = QComboBox()
        self.sub_lang.addItems(["id", "en"])
        sub_row.addWidget(self.sub_lang)
        self.sub_fmt = QComboBox()
        self.sub_fmt.addItems(["srt", "vtt", "ass"])
        sub_row.addWidget(self.sub_fmt)
        sub_v.addLayout(sub_row)
        row_settings_2.addWidget(sub_box)

        thm_box = QFrame()
        thm_box.setStyleSheet("background-color: #1f2335; border-radius: 6px; padding: 5px;")
        thm_v = QVBoxLayout(thm_box)
        thm_v.setContentsMargins(6, 4, 6, 4)
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
        dir_h = QHBoxLayout()
        dir_lbl = QLabel("📂 Simpan ke:")
        dir_lbl.setStyleSheet("color: #c0caf5; font-weight: bold;")
        dir_h.addWidget(dir_lbl)

        self.dir_in = QLineEdit()
        self.dir_in.setText(Config.load_last_directory())
        dir_h.addWidget(self.dir_in, 1)

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

        # 6. Panel Live Log Console (Lengkap dengan Tombol Salin, Buka File Log, Bersihkan)
        log_header_row = QHBoxLayout()
        log_title = QLabel("🖥️ Log Aktivitas & Detail Error Lengkap (Live Console):")
        log_title.setStyleSheet("font-weight: bold; color: #7aa2f7;")
        log_header_row.addWidget(log_title)
        log_header_row.addStretch()

        btn_copy_log = QPushButton("📋 Salin Log")
        btn_copy_log.setCursor(QCursor(Qt.PointingHandCursor))
        btn_copy_log.setStyleSheet("background-color: #24283b; border: 1px solid #414868; color: #c0caf5; padding: 4px 10px; font-size: 11px;")
        btn_copy_log.clicked.connect(self.copy_logs)
        log_header_row.addWidget(btn_copy_log)

        btn_open_log_dir = QPushButton("📄 Buka Folder File Log")
        btn_open_log_dir.setCursor(QCursor(Qt.PointingHandCursor))
        btn_open_log_dir.setStyleSheet("background-color: #24283b; border: 1px solid #414868; color: #c0caf5; padding: 4px 10px; font-size: 11px;")
        btn_open_log_dir.clicked.connect(self.open_log_folder)
        log_header_row.addWidget(btn_open_log_dir)

        btn_clear_log = QPushButton("🗑️ Bersihkan Log")
        btn_clear_log.setCursor(QCursor(Qt.PointingHandCursor))
        btn_clear_log.setStyleSheet("background-color: #24283b; border: 1px solid #414868; color: #f7768e; padding: 4px 10px; font-size: 11px;")
        btn_clear_log.clicked.connect(lambda: self.log_console.clear())
        log_header_row.addWidget(btn_clear_log)

        self.main_layout.addLayout(log_header_row)

        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setObjectName("log_console")
        self.log_console.setMinimumHeight(145)
        self.main_layout.addWidget(self.log_console, 1)

        # 7. Status & Progress Bar
        status_row = QHBoxLayout()
        self.status = QLabel("Status: Siap")
        self.status.setStyleSheet("font-weight: bold; color: #7aa2f7; font-size: 13px;")
        status_row.addWidget(self.status)
        status_row.addStretch()
        self.detail_stats = QLabel("Kecepatan: -- | Sisa Waktu: -- | Ukuran: --")
        self.detail_stats.setStyleSheet("color: #7982a9; font-size: 12px;")
        status_row.addWidget(self.detail_stats)
        self.main_layout.addLayout(status_row)

        self.p_bar = QProgressBar()
        self.p_bar.setValue(0)
        self.main_layout.addWidget(self.p_bar)

        # 8. Tombol Eksekusi Utama
        self.dl_btn = QPushButton("🚀 MULAI UNDUH SEKARANG")
        self.dl_btn.setObjectName("download_btn")
        self.dl_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.dl_btn.clicked.connect(self.run_dl)
        self.main_layout.addWidget(self.dl_btn)

    # --- FUNGSI LOGGING REAL-TIME ---
    def append_log(self, level: str, message: str):
        ts = time.strftime("%H:%M:%S")
        color_map = {
            "INFO": "#7dcfff",
            "SUCCESS": "#9ece6a",
            "WARNING": "#e0af68",
            "ERROR": "#f7768e",
        }
        color = color_map.get(level.upper(), "#c0caf5")
        escaped_msg = html.escape(str(message)).replace("\n", "<br>")
        formatted = f"<span style='color:#565f89;'>[{ts}]</span> <b style='color:{color};'>[{level.upper()}]</b> <span style='color:{color};'>{escaped_msg}</span>"
        self.log_console.append(formatted)
        self.log_console.moveCursor(QTextCursor.End)

    def copy_logs(self):
        QApplication.clipboard().setText(self.log_console.toPlainText())
        self.append_log("INFO", "Seluruh isi log berhasil disalin ke Clipboard.")

    def open_log_folder(self):
        log_dir = os.path.join(Config.get_app_data_dir(), "logs")
        os.makedirs(log_dir, exist_ok=True)
        os.startfile(log_dir)

    # --- FUNGSI EKSTENSI & AUTENTIKASI ---
    def check_extension_heartbeat(self):
        last_seen = bridge_state.get("last_seen", 0.0)
        is_alive = (time.time() - last_seen) < 12.0
        if is_alive != self.extension_connected:
            self.update_extension_badge(is_alive)

    def update_extension_badge(self, connected: bool):
        was_connected = self.extension_connected
        self.extension_connected = connected
        if connected:
            self.ext_status_badge.setText("🟢 Ekstensi: Terhubung (Aktif)")
            self.ext_status_badge.setStyleSheet(
                "background-color: #24283b; color: #9ece6a; border: 1px solid #9ece6a; "
                "border-radius: 6px; padding: 6px 10px; font-weight: bold; font-size: 12px;"
            )
            if not was_connected:
                self.append_log("SUCCESS", "🧩 Ekstensi browser Kawaragi Trigger terdeteksi & terhubung!")
        else:
            self.ext_status_badge.setText("🔴 Ekstensi: Belum Terhubung")
            self.ext_status_badge.setStyleSheet(
                "background-color: #24283b; color: #f7768e; border: 1px solid #f7768e; "
                "border-radius: 6px; padding: 6px 10px; font-weight: bold; font-size: 12px;"
            )

    def open_extension_helper(self):
        dialog = ExtensionHelperDialog(is_connected=self.extension_connected, parent=self)
        dialog.exec_()

    def on_auth_mode_changed(self, idx):
        mode = self.auth_drop.currentData()
        if mode == "file":
            f_path, _ = QFileDialog.getOpenFileName(self, "Pilih File cookies.txt (Format Netscape)", "", "Text Files (*.txt);;All Files (*)")
            if f_path and os.path.isfile(f_path):
                self.manual_cookie_path = f_path
                self.cookie_file = f_path
                self.append_log("INFO", f"📄 File cookies manual dipilih: {f_path}")
            else:
                self.auth_drop.setCurrentIndex(0)

    def resolve_active_cookie_source(self) -> str:
        mode = self.auth_drop.currentData()
        if mode == "file" and self.manual_cookie_path and os.path.isfile(self.manual_cookie_path):
            return self.manual_cookie_path
        elif mode in ("edge", "firefox", "brave", "chrome"):
            return mode
        elif mode == "extension":
            if self.cookie_file and self.cookie_file.endswith(".txt") and os.path.isfile(self.cookie_file):
                return self.cookie_file
            return "Tanpa Login"
        else:
            # Jika baru saja sinkronisasi dari ekstensi, gunakan file cookie dari ekstensi
            if self.cookie_file and self.cookie_file.endswith(".txt") and os.path.isfile(self.cookie_file):
                return self.cookie_file
            return "Tanpa Login"

    def on_tab_received_from_extension(self):
        """Dipanggil saat pengguna menekan tombol 'Kirim Tab Ini ke Kawaragi' di popup ekstensi Chrome."""
        tab_url = received_cookies_cache.get("tab_url", "").strip()
        tab_title = received_cookies_cache.get("tab_title", "")
        cookies_text = received_cookies_cache.get("current", "")
        count = received_cookies_cache.get("count", 0)
        self.custom_user_agent = received_cookies_cache.get("userAgent", "")

        if cookies_text:
            app_data_dir = Config.get_app_data_dir()
            self.cookie_file = os.path.join(app_data_dir, "temp_cookies.txt")
            try:
                with open(self.cookie_file, "w", encoding="utf-8") as f:
                    f.write(cookies_text)
            except Exception as e:
                logger.error(f"Gagal menyimpan temp_cookies.txt: {e}")

        self.append_log("SUCCESS", f"🚀 Menerima tautan dari tab browser: {tab_title or tab_url} ({count} cookies tersinkronisasi)")
        if tab_url:
            self.url_input.setText(tab_url)
            self.activateWindow()
            self.raise_()
            self.launch_info_worker(tab_url, self.cookie_file)

    # --- FUNGSI UTAMA UI ---
    def paste_from_clipboard(self):
        clipboard = QApplication.clipboard()
        text = clipboard.text().strip()
        if text:
            self.url_input.setText(text)
            self.append_log("INFO", f"📋 Tautan ditempel dari clipboard: {text}")
            if is_valid_url(text):
                self.start_info_check(force_extension=False)
        else:
            QMessageBox.information(self, "Clipboard Kosong", "Tidak ada teks tautan di clipboard.")

    def browse_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Pilih Folder Penyimpanan")
        if d:
            self.dir_in.setText(d)
            Config.save_last_directory(d)
            self.append_log("INFO", f"📂 Folder tujuan diubah ke: {d}")

    def open_current_directory(self):
        d = self.dir_in.text()
        if os.path.exists(d):
            os.startfile(d)
        else:
            QMessageBox.warning(self, "Folder Tidak Ditemukan", f"Folder tidak ada:\n{d}")

    def open_history(self):
        dialog = HistoryDialog(self)
        dialog.exec_()

    def start_info_check(self, force_extension=False):
        url = self.url_input.text().strip()
        if not is_valid_url(url):
            QMessageBox.warning(self, "URL Tidak Valid", "Silakan masukkan tautan video yang benar (contoh: https://...)")
            return

        self.is_checking_info = True
        self.pending_action_after_cookies = "info"
        self.info_btn.setEnabled(False)
        self.trigger_btn.setEnabled(False)
        self.btn_cancel_action.setEnabled(True)

        use_ext = force_extension or (self.auth_drop.currentData() == "extension")
        if use_ext:
            self.trigger_timeout_counter = 0
            received_cookies_cache["current"] = ""
            current_task["url"] = url
            self.status.setText("Status: Meminta cookies dari ekstensi browser...")
            self.append_log("INFO", f"🛡️ Memicu ekstensi browser untuk mengambil cookies tautan: {url}")
            self.loading_timer.start(100)
        else:
            cookie_src = self.resolve_active_cookie_source()
            self.status.setText("Status: Mengambil informasi video...")
            self.launch_info_worker(url, cookie_src)

    def launch_info_worker(self, url, cookie_file):
        self.info_worker = InfoWorker(url, cookie_file, self.custom_user_agent)
        self.info_worker.log_msg.connect(self.append_log)
        self.info_worker.finished.connect(self.on_info_ok)
        self.info_worker.error.connect(self.on_error)
        self.info_worker.start()

    def on_cookies_received(self):
        self.loading_timer.stop()
        cookies_text = received_cookies_cache.get("current", "")
        count = received_cookies_cache.get("count", 0)
        self.custom_user_agent = received_cookies_cache.get("userAgent", "")

        app_data_dir = Config.get_app_data_dir()
        if cookies_text and count > 0:
            self.cookie_file = os.path.join(app_data_dir, "temp_cookies.txt")
            try:
                with open(self.cookie_file, "w", encoding="utf-8") as f:
                    f.write(cookies_text)
                self.append_log("SUCCESS", f"🔑 Berhasil menerima {count} cookies dari ekstensi browser!")
            except Exception as e:
                logger.error(f"Gagal menulis cookie_file: {e}")
                self.append_log("ERROR", f"Gagal menyimpan file cookies sementara: {e}")
        else:
            self.cookie_file = "Tanpa Login"
            self.append_log("WARNING", "Ekstensi terhubung tetapi tidak ada cookies login pada domain tersebut. Melanjutkan tanpa login.")

        self.status.setText("Status: Cookies diterima! Memuat informasi video...")
        url = self.url_input.text().strip()
        if is_valid_url(url):
            self.launch_info_worker(url, self.cookie_file)
        else:
            self.info_btn.setEnabled(True)
            self.trigger_btn.setEnabled(True)
            self.btn_cancel_action.setEnabled(False)

    def animate_loading(self):
        frame = self.loading_frames[self.loading_step % len(self.loading_frames)]
        self.loading_step += 1
        self.trigger_timeout_counter += 1

        seconds_elapsed = self.trigger_timeout_counter // 10
        self.info_box.setText(
            f"<p align='center'><span style='font-size:22px; color:#bb9af7;'>{frame}</span><br>"
            f"<b>Menghubungi Ekstensi Browser Kawaragi Trigger... ({seconds_elapsed}s)</b><br>"
            f"<span style='font-size:11px; color:#7982a9;'>Jika ekstensi belum dipasang, klik tombol '🧩 Pasang Ekstensi' di kanan atas.</span></p>"
        )

        # Timeout 5 detik: otomatis fallback ke ekstraksi langsung
        if self.trigger_timeout_counter >= 50:
            self.loading_timer.stop()
            self.append_log("WARNING", "⏱️ Ekstensi browser belum merespons dalam 5 detik. Otomatis melanjutkan tanpa ekstensi (klik '🧩 Pasang Ekstensi' jika ingin mengaktifkan).")
            self.status.setText("Status: Ekstensi belum aktif, melanjutkan secara langsung...")
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
        extractor = info.get('extractor', 'Video')
        fmt_count = info.get('formats_count', 0)

        if "thumbnail_bytes" in info and info["thumbnail_bytes"]:
            pixmap = QPixmap()
            pixmap.loadFromData(info["thumbnail_bytes"])
            if not pixmap.isNull():
                self.thumb_preview.setPixmap(
                    pixmap.scaled(self.thumb_preview.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                )
        else:
            self.thumb_preview.setText(f"🎬 {extractor}")

        self.info_box.setText(
            f"<b>{html.escape(title)}</b><br>"
            f"<span style='color:#7aa2f7;'>Platform:</span> {html.escape(extractor)} &nbsp;|&nbsp; "
            f"<span style='color:#7aa2f7;'>Channel:</span> {html.escape(uploader)} &nbsp;|&nbsp; "
            f"<span style='color:#7aa2f7;'>Durasi:</span> {dur_str} &nbsp;|&nbsp; "
            f"<span style='color:#9ece6a;'>{fmt_count} Stream Tersedia</span>"
        )

        subs = info.get('subtitles', [])
        if subs:
            self.sub_lang.clear()
            self.sub_lang.addItems(subs)
            self.sub_cb.setEnabled(True)
        else:
            self.sub_lang.clear()
            self.sub_lang.addItem("Tidak ada")

        self.status.setText("Status: Informasi video berhasil dimuat! Siap diunduh.")

    def run_dl(self):
        url = self.url_input.text().strip()
        if not is_valid_url(url):
            QMessageBox.warning(self, "URL Kosong", "Masukkan tautan video yang valid terlebih dahulu!")
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
        cookie_src = self.resolve_active_cookie_source()

        p = {
            'url': url,
            'out_dir': out_dir,
            'quality': quality_val,
            'cookies_data': cookie_src,
            'user_agent': self.custom_user_agent,
            'inc_sub': self.sub_cb.isChecked(),
            'sub_lang': self.sub_lang.currentText(),
            'sub_fmt': self.sub_fmt.currentText(),
            'inc_thm': self.thm_cb.isChecked(),
            'thm_fmt': self.thm_fmt.currentText(),
            'target_fmt': target_fmt
        }

        self.download_worker = DownloadWorker(p)
        self.download_worker.log_msg.connect(self.append_log)
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

        title = self.current_video_info.get("title") or os.path.basename(file_path)
        Config.save_history_entry({
            "title": title,
            "url": self.url_input.text().strip(),
            "file_path": file_path,
            "duration": self.current_video_duration,
            "format": self.fmt_drop.currentText()
        })

        if self.ss_cb.isChecked() and self.current_video_duration > 0:
            self.status.setText("Status: Mengambil cuplikan screenshot acak...")
            self.proc = ProcessingWorker(
                "screenshot",
                file_path,
                count=self.ss_count.value(),
                duration=self.current_video_duration,
                dir=self.dir_in.text()
            )
            self.proc.log_msg.connect(self.append_log)
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
            self.append_log("SUCCESS", f"📸 {saved_count} screenshot disimpan ke {main_dir}")
        else:
            for path in shot_paths:
                try:
                    os.remove(path)
                except Exception:
                    pass
            self.status.setText("Status: Seluruh screenshot dibatalkan.")

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
                self.proc.log_msg.connect(self.append_log)
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
        self.append_log("SUCCESS", f"✅ Seluruh proses selesai! Lokasi file: {final_file_path}")

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
            self.append_log("WARNING", "⏹ Pemeriksaan tautan dibatalkan oleh pengguna.")

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

        self.status.setText("Status: Gagal (Lihat Log Aktivitas di atas untuk detail).")
        self.detail_stats.setText("Terjadi kesalahan pada proses.")
        self.info_box.setText(
            f"<span style='color:#f7768e;'><b>❌ Terjadi Kesalahan:</b><br>{html.escape(str(msg))}</span><br>"
            f"<span style='color:#7982a9; font-size:11px;'>💡 Tip: Jika situs membutuhkan login/verifikasi bot, pilih metode Autentikasi Cookies atau gunakan tombol '🧩 Pasang Ekstensi'.</span>"
        )
        self.append_log("ERROR", f"Proses berhenti karena error: {msg}")

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
                font-size: 21px; 
                font-weight: bold; 
            }
            QFrame#preview_frame, QFrame#opt_group {
                background-color: #24283b;
                border: 1px solid #414868;
                border-radius: 8px;
            }
            QLabel#info_box { 
                color: #c0caf5; 
                font-size: 13px;
            }
            QTextEdit#log_console {
                background-color: #16161e;
                color: #c0caf5;
                border: 1px solid #414868;
                border-radius: 8px;
                padding: 8px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
            }
            QLineEdit, QComboBox, QSpinBox { 
                background-color: #1f2335; 
                color: #c0caf5; 
                border: 1px solid #414868; 
                border-radius: 6px; 
                padding: 6px 10px; 
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
                padding: 8px 14px; 
                font-weight: bold; 
                font-size: 13px;
                border: none;
            }
            QPushButton:hover {
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
                padding: 11px; 
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
                height: 18px;
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
                width: 17px; 
                height: 17px; 
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
        if hasattr(self, 'bridge_server') and self.bridge_server:
            self.bridge_server.stop()

        cookie_path = os.path.join(Config.get_app_data_dir(), 'temp_cookies.txt')
        if os.path.exists(cookie_path):
            try:
                os.remove(cookie_path)
            except Exception:
                pass

        event.accept()