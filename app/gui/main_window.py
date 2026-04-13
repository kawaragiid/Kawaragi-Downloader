import json, os, shutil, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from PyQt5.QtWidgets import *
from PyQt5.QtGui import QPixmap, QCursor, QIcon, QImage
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer, QSize
from app.core.downloader import Downloader
from app.core.ffmpeg_handler import FFmpegHandler
from app.utils.validation import is_valid_url
from app.core.config import Config
from app.utils.log_utils import setup_logger

logger = setup_logger("main_window", "app.log")
current_task = {"url": None}
received_cookies_cache = {"current": ""}

# --- FUNGSI AJAIB PENUNJUK JALAN LOGO ---
def get_asset_path(filename):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, "assets", filename)

# --- UI PREVIEW SCREENSHOT ---
class ScreenshotPreviewDialog(QDialog):
    def __init__(self, image_paths, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pilih Screenshot untuk Disimpan")
        self.resize(1000, 700)
        self.setModal(True)
        self.apply_theme()
        
        self.layout = QVBoxLayout(self)
        label = QLabel("Centang gambar yang ingin Anda simpan:")
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
            vbox.setContentsMargins(5, 5, 5, 5)
            
            img_label = QLabel()
            pixmap = QPixmap(path)
            img_label.setPixmap(pixmap.scaled(300, 168, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            img_label.setAlignment(Qt.AlignCenter)
            vbox.addWidget(img_label)
            
            cb = QCheckBox(f"Simpan Gambar {i+1}")
            cb.setChecked(True) 
            cb.setCursor(QCursor(Qt.PointingHandCursor))
            cb.setProperty("file_path", path)
            vbox.addWidget(cb)
            self.checkboxes.append(cb)
            self.grid.addWidget(container, row, col)

        btn_layout = QHBoxLayout()
        self.btn_save = QPushButton("Simpan yang Dipilih")
        self.btn_save.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_save.setStyleSheet("background-color: #9ece6a; color: #1a1b26;")
        self.btn_save.clicked.connect(self.accept)
        
        self.btn_cancel = QPushButton("Hapus Semua")
        self.btn_cancel.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_cancel.setStyleSheet("background-color: #f7768e; color: white;")
        self.btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_save)
        self.layout.addLayout(btn_layout)

    def get_selected_files(self):
        selected = []
        for cb in self.checkboxes:
            if cb.isChecked(): selected.append(cb.property("file_path"))
        return selected

    def apply_theme(self):
        self.setStyleSheet("""
            QDialog { background-color: #1a1b26; }
            QLabel { color: #a9b1d6; font-family: 'Segoe UI'; }
            QScrollArea { border: none; background-color: transparent; }
            QWidget#scroll_content { background-color: transparent; }
            QPushButton { border-radius: 6px; padding: 10px 20px; font-weight: bold; font-size: 14px; }
            QCheckBox { color: #a9b1d6; padding: 5px; font-size: 13px; }
            QCheckBox::indicator { width: 18px; height: 18px; }
        """)

# --- SERVER LOKAL & THREAD WORKERS ---
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

    def do_POST(self):
        if self.path == '/submit-cookies':
            data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            received_cookies_cache["current"] = data.get('cookies', "")
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.server.gui_signal.emit()

    def do_OPTIONS(self):
        self.send_response(200); self.send_header('Access-Control-Allow-Origin', '*'); self.end_headers()

class BridgeServer(QThread):
    cookies_ready_signal = pyqtSignal()
    def run(self):
        server_address = ('127.0.0.1', 65432)
        httpd = ThreadingHTTPServer(server_address, BridgeHandler)
        httpd.gui_signal = self.cookies_ready_signal
        httpd.serve_forever()

class InfoWorker(QThread):
    finished = pyqtSignal(dict); error = pyqtSignal(str)
    def __init__(self, url, cookies):
        super().__init__(); self.url = url; self.cookies = cookies
    def run(self):
        d = Downloader(error_callback=lambda e: self.error.emit(e))
        info = d.get_video_info(self.url, self.cookies)
        if info: self.finished.emit(info)

class DownloadWorker(QThread):
    progress = pyqtSignal(int); done = pyqtSignal(str); error = pyqtSignal(str)
    def __init__(self, params):
        super().__init__(); self.p = params
    def run(self):
        d = Downloader(progress_callback=self.progress.emit, completion_callback=self.done.emit, error_callback=self.error.emit)
        d.download(self.p['url'], None, self.p['inc_sub'], self.p['sub_lang'], self.p['sub_fmt'], False, None, self.p['out_dir'], self.p['cookies_data'])

class ProcessingWorker(QThread):
    finished = pyqtSignal(object); error = pyqtSignal(str)
    def __init__(self, mode, input_file, **kwargs):
        super().__init__(); self.mode = mode; self.input_file = input_file; self.kwargs = kwargs
    def run(self):
        try:
            handler = FFmpegHandler()
            if self.mode == "convert":
                res = handler.convert(self.input_file, self.kwargs['ext'])
                self.finished.emit(res)
            elif self.mode == "screenshot":
                res = handler.take_random_screenshots(self.input_file, self.kwargs['count'], self.kwargs['duration'], self.kwargs['dir'])
                self.finished.emit(res)
        except Exception as e: self.error.emit(str(e))

# --- KELAS JENDELA UTAMA ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Kawaragi Downloader"); self.resize(850, 850)
        
        logo_ico = get_asset_path("logo.ico")
        logo_png = get_asset_path("logo.png")
        self.final_logo = logo_ico if os.path.exists(logo_ico) else logo_png
        self.setWindowIcon(QIcon(self.final_logo))
        
        self.apply_modern_theme()
        self.bridge_server = BridgeServer(); self.bridge_server.cookies_ready_signal.connect(self.on_cookies_received); self.bridge_server.start()
        self.setup_ui()
        self.loading_timer = QTimer(self); self.loading_timer.timeout.connect(self.animate_loading)
        self.loading_step = 0
        self.loading_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.current_video_duration = 0

    def setup_ui(self):
        self.central_widget = QWidget(); self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget); self.main_layout.setContentsMargins(30, 20, 30, 20); self.main_layout.setSpacing(12)
        
        header = QHBoxLayout(); logo = QLabel()
        pix = QPixmap(self.final_logo)
        if not pix.isNull(): logo.setPixmap(pix); logo.setFixedSize(50, 50); logo.setScaledContents(True)
        header.addWidget(logo); title = QLabel("Kawaragi Downloader"); title.setObjectName("app_title"); header.addWidget(title); header.addStretch(); self.main_layout.addLayout(header)

        self.main_layout.addWidget(QLabel("Tempel Link Video (YouTube, TikTok, dll):"))
        self.url_input = QLineEdit(); self.url_input.setPlaceholderText("https://..."); self.main_layout.addWidget(self.url_input)
        self.info_btn = QPushButton("CEK LINK & TRIGGER EKSTENSI"); self.info_btn.setCursor(QCursor(Qt.PointingHandCursor)); self.info_btn.clicked.connect(self.start_trigger); self.main_layout.addWidget(self.info_btn)
        self.info_box = QLabel("Menunggu input link..."); self.info_box.setObjectName("info_box"); self.info_box.setWordWrap(True); self.main_layout.addWidget(self.info_box)

        row1 = QHBoxLayout()
        f_v = QVBoxLayout(); f_v.addWidget(QLabel("Format Tujuan Rendering:")); self.fmt_drop = QComboBox(); self.fmt_drop.addItems(["Otomatis", "mp4", "webm", "mp3", "aac"]); f_v.addWidget(self.fmt_drop); row1.addLayout(f_v)
        s_v = QVBoxLayout(); self.ss_cb = QCheckBox("Ambil Screenshot Acak"); s_v.addWidget(self.ss_cb); hbox_ss = QHBoxLayout(); hbox_ss.addWidget(QLabel("Jumlah:")); self.ss_count = QSpinBox(); self.ss_count.setRange(1, 30); self.ss_count.setValue(6); hbox_ss.addWidget(self.ss_count); hbox_ss.addStretch(); s_v.addLayout(hbox_ss); row1.addLayout(s_v)
        self.main_layout.addLayout(row1)

        row2 = QHBoxLayout()
        sub_v = QVBoxLayout(); self.sub_cb = QCheckBox("Unduh Subtitle"); sub_v.addWidget(self.sub_cb); self.sub_lang = QComboBox(); self.sub_lang.setPlaceholderText("Bahasa"); sub_v.addWidget(self.sub_lang); self.sub_fmt = QComboBox(); self.sub_fmt.addItems(["srt", "vtt", "ass"]); sub_v.addWidget(self.sub_fmt); row2.addLayout(sub_v)
        thm_v = QVBoxLayout(); self.thm_cb = QCheckBox("Unduh Thumbnail"); thm_v.addWidget(self.thm_cb); self.thm_fmt = QComboBox(); self.thm_fmt.addItems(["jpg", "png", "webp"]); thm_v.addWidget(self.thm_fmt); thm_v.addStretch(); row2.addLayout(thm_v)
        self.main_layout.addLayout(row2)

        self.main_layout.addWidget(QLabel("Simpan ke:")); dir_h = QHBoxLayout(); self.dir_in = QLineEdit(); self.dir_in.setText(Config.load_last_directory()); dir_h.addWidget(self.dir_in); btn_b = QPushButton("Ganti Folder"); btn_b.setCursor(QCursor(Qt.PointingHandCursor)); btn_b.clicked.connect(self.browse); dir_h.addWidget(btn_b); self.main_layout.addLayout(dir_h)

        self.main_layout.addStretch()
        self.status = QLabel("Status: Idle"); self.main_layout.addWidget(self.status)
        self.p_bar = QProgressBar(); self.main_layout.addWidget(self.p_bar)
        self.dl_btn = QPushButton("MULAI UNDUH BRUTAL"); self.dl_btn.setObjectName("download_btn"); self.dl_btn.setCursor(QCursor(Qt.PointingHandCursor)); self.dl_btn.clicked.connect(self.run_dl); self.main_layout.addWidget(self.dl_btn)

    def browse(self):
        d = QFileDialog.getExistingDirectory(self, "Pilih Folder")
        if d: self.dir_in.setText(d); Config.save_last_directory(d)

    def start_trigger(self):
        url = self.url_input.text()
        if not is_valid_url(url): QMessageBox.warning(self, "URL Salah", "URL tidak valid!"); return
        received_cookies_cache["current"] = ""; current_task["url"] = url; self.info_btn.setEnabled(False); self.loading_timer.start(100)

    def on_cookies_received(self):
        self.loading_timer.stop()
        self.status.setText("Status: Kunci diterima!")
        cookies_text = received_cookies_cache["current"]
        
        # PERBAIKAN: Menyimpan cookie langsung ke AppData
        app_data_dir = os.path.join(os.getenv('LOCALAPPDATA'), 'KawaragiDownloader')
        os.makedirs(app_data_dir, exist_ok=True)
        self.cookie_file = os.path.join(app_data_dir, "temp_cookies.txt") if cookies_text else "Tanpa Login"
        
        if cookies_text:
            with open(self.cookie_file, "w", encoding="utf-8") as f: 
                f.write(cookies_text)
                
        self.info_worker = InfoWorker(self.url_input.text(), self.cookie_file)
        self.info_worker.finished.connect(self.on_info_ok)
        self.info_worker.error.connect(self.on_error)
        self.info_worker.start()

    def on_info_ok(self, info):
        self.info_btn.setEnabled(True)
        self.current_video_duration = info['duration']
        self.info_box.setText(f"<b>🎥 {info['title']}</b><br>⏱️ {info['duration']} detik")
        if info['subtitles']: self.sub_lang.clear(); self.sub_lang.addItems(info['subtitles'])

    def run_dl(self):
        if not is_valid_url(self.url_input.text()): return
        self.dl_btn.setEnabled(False); self.status.setText("Status: Menembus pertahanan & mengunduh..."); self.p_bar.setValue(0)
        p = {
            'url': self.url_input.text(), 'out_dir': self.dir_in.text(), 
            'cookies_data': getattr(self, 'cookie_file', "Tanpa Login"),
            'inc_sub': self.sub_cb.isChecked(), 'sub_lang': self.sub_lang.currentText(), 'sub_fmt': self.sub_fmt.currentText()
        }
        self.worker = DownloadWorker(p); self.worker.progress.connect(self.p_bar.setValue); self.worker.done.connect(self.on_dl_done); self.worker.error.connect(self.on_error); self.worker.start()

    def on_dl_done(self, file_path):
        self.temp_video_file = file_path
        if self.ss_cb.isChecked() and self.current_video_duration > 0:
            self.status.setText("Status: Mengambil screenshot acak sepanjang video...")
            self.proc = ProcessingWorker("screenshot", file_path, count=self.ss_count.value(), duration=self.current_video_duration, dir=self.dir_in.text())
            self.proc.finished.connect(self.show_ss_preview); self.proc.error.connect(self.on_error); self.proc.start()
        else: self.ask_convert(file_path)

    def show_ss_preview(self, shot_paths):
        if not shot_paths:
            self.ask_convert(self.temp_video_file)
            return

        dialog = ScreenshotPreviewDialog(shot_paths, self)
        result = dialog.exec_() 
        
        if result == QDialog.Accepted:
            selected_files = dialog.get_selected_files()
            main_dir = self.dir_in.text()
            saved_count = 0
            for path in shot_paths:
                if path in selected_files:
                    filename = os.path.basename(path)
                    new_path = os.path.join(main_dir, f"kawaragi_{filename}")
                    try:
                        shutil.move(path, new_path)
                        saved_count += 1
                    except: pass
                else:
                    try: os.remove(path)
                    except: pass
            
            temp_dir = os.path.dirname(shot_paths[0])
            if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
            self.status.setText(f"Status: {saved_count} screenshot disimpan.")
        else:
            if shot_paths:
                temp_dir = os.path.dirname(shot_paths[0])
                if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
            self.status.setText("Status: Semua screenshot dihapus.")
            
        self.ask_convert(self.temp_video_file)

    def ask_convert(self, file_path):
        target = self.fmt_drop.currentText()
        actual = os.path.splitext(file_path)[1].replace(".", "")
        if target != "Otomatis" and actual != target:
            reply = QMessageBox.question(self, 'Konversi Format', f"File selesai diunduh sebagai <b>{actual}</b>.<br>Ingin di-render ulang ke <b>{target}</b> via FFmpeg?", QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if reply == QMessageBox.Yes:
                self.status.setText(f"Status: Merender ke {target}...")
                self.proc = ProcessingWorker("convert", file_path, ext=target)
                self.proc.finished.connect(self.final_step); self.proc.error.connect(self.on_error); self.proc.start()
                return
        self.final_step(file_path)

    def final_step(self, path):
        self.dl_btn.setEnabled(True); self.status.setText("Status: Selesai!"); self.p_bar.setValue(100)
        QMessageBox.information(self, "Berhasil", f"Proses Selesai!<br>File: {path}")

    def on_error(self, msg):
        self.loading_timer.stop(); self.info_btn.setEnabled(True); self.dl_btn.setEnabled(True)
        self.status.setText("Status: Gagal."); self.info_box.setText(f"<span style='color:#f7768e;'>{msg}</span>")

    def animate_loading(self):
        frame = self.loading_frames[self.loading_step % len(self.loading_frames)]
        self.info_box.setText(f"<p align='center'><span style='font-size:30px; color:#7aa2f7;'>{frame}</span><br>Memicu Ekstensi...</p>")
        self.loading_step += 1

    def apply_modern_theme(self):
        self.setStyleSheet("""
            QMainWindow, QWidget#central_widget { background-color: #1a1b26; }
            QLabel { color: #a9b1d6; font-family: 'Segoe UI'; font-size: 13px; }
            QLabel#app_title { color: #7aa2f7; font-size: 26px; font-weight: bold; }
            QLabel#info_box { background-color: #24283b; border-radius: 10px; padding: 15px; color: #c0caf5; border: 1px solid #414868; min-height: 80px; }
            QLineEdit, QComboBox, QSpinBox { background-color: #24283b; color: #c0caf5; border: 1px solid #414868; border-radius: 6px; padding: 6px; }
            QPushButton { background-color: #3d59a1; color: white; border-radius: 6px; padding: 10px; font-weight: bold; }
            QPushButton#download_btn { background-color: #9ece6a; color: #1a1b26; font-size: 16px; padding: 12px; }
            QProgressBar { border: 1px solid #414868; border-radius: 10px; background-color: #24283b; text-align: center; color: white; height: 18px;}
            QProgressBar::chunk { background-color: #7aa2f7; border-radius: 9px; }
            QCheckBox { color: #a9b1d6; font-size: 13px; }
        """)

    def closeEvent(self, event):
        # PERBAIKAN: Hapus cookie dari AppData saat aplikasi ditutup
        cookie_path = os.path.join(os.getenv('LOCALAPPDATA'), 'KawaragiDownloader', 'temp_cookies.txt')
        if os.path.exists(cookie_path): 
            try:
                os.remove(cookie_path)
            except:
                pass
        event.accept()