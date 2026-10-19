import unittest
import os
import sys
import time
import requests

if hasattr(sys.stdout, "reconfigure") and sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure") and sys.stderr is not None:
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from PyQt5.QtWidgets import QApplication
from app.core.downloader import Downloader
from app.utils.validation import is_valid_url
from app.utils.file_utils import get_ffmpeg_path, get_extension_dir, format_bytes, format_seconds
from app.core.config import Config
from app.gui.main_window import MainWindow, current_task, received_cookies_cache, bridge_state

app = QApplication.instance() or QApplication(sys.argv)


class TestKawaragiSystem(unittest.TestCase):
    def setUp(self):
        self.logs = []
        self.downloader = Downloader(log_callback=lambda lvl, msg: self.logs.append((lvl, msg)))

    def test_valid_url(self):
        valid_urls = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "http://youtu.be/dQw4w9WgXcQ",
            "https://www.bilibili.com/video/BV1cdpc6PErN/",
            "https://www.bilibili.tv/en/video/4797844121458181",
            "https://tiktok.com/@user/video/123456",
            "https://instagram.com/p/abcdef"
        ]
        invalid_urls = ["invalid_url", "ftp://bad", "", "notaurl"]
        for url in valid_urls:
            self.assertTrue(is_valid_url(url), f"Should be valid: {url}")
        for url in invalid_urls:
            self.assertFalse(is_valid_url(url), f"Should be invalid: {url}")

    def test_ffmpeg_and_extension_files(self):
        ffmpeg_path = get_ffmpeg_path()
        self.assertTrue(os.path.isfile(ffmpeg_path), f"FFmpeg harus ditemukan: {ffmpeg_path}")

        ext_dir = get_extension_dir()
        self.assertTrue(os.path.isdir(ext_dir), f"Folder ekstensi harus ada: {ext_dir}")
        for req_file in ["manifest.json", "background.js", "popup.html", "popup.js", "install_extension.bat", "logo.png"]:
            self.assertTrue(
                os.path.isfile(os.path.join(ext_dir, req_file)),
                f"File ekstensi {req_file} harus tersedia di {ext_dir}"
            )

    def test_format_selectors_vertical_and_horizontal(self):
        fmt_1080 = self.downloader._get_format_string("1080p")
        self.assertIn("height<=1080", fmt_1080)
        self.assertIn("width<=1080", fmt_1080)
        self.assertTrue(fmt_1080.endswith("/bv*+ba/b"))

        fmt_audio = self.downloader._get_format_string("audio_320")
        self.assertEqual(fmt_audio, "ba/b")

    def test_gui_and_extension_bridge_communication(self):
        win = MainWindow()
        try:
            # Tunggu sejenak agar BridgeServer siap di 127.0.0.1:65432
            time.sleep(0.3)

            # 1. Uji /ping dari ekstensi
            r_ping = requests.get("http://127.0.0.1:65432/ping", timeout=3)
            self.assertEqual(r_ping.status_code, 200)
            self.assertEqual(r_ping.json().get("status"), "ready")
            self.assertGreater(bridge_state["last_seen"], 0)

            # 2. Uji pengambilan task (/get-task) oleh ekstensi
            current_task["url"] = "https://www.bilibili.com/video/BV1cdpc6PErN/"
            r_task = requests.get("http://127.0.0.1:65432/get-task", timeout=3)
            self.assertEqual(r_task.status_code, 200)
            self.assertEqual(r_task.json().get("url"), "https://www.bilibili.com/video/BV1cdpc6PErN/")

            # 3. Uji pengiriman cookies (/submit-cookies) dari ekstensi ke Desktop
            sample_cookie = "# Netscape HTTP Cookie File\n.bilibili.com\tTRUE\t/\tTRUE\t1999999999\tSESSDATA\tdummy_sess\n"
            r_post = requests.post(
                "http://127.0.0.1:65432/submit-cookies",
                json={"cookies": sample_cookie, "count": 1, "userAgent": "Mozilla/5.0 TestAgent"},
                timeout=3
            )
            self.assertEqual(r_post.status_code, 200)
            self.assertEqual(received_cookies_cache["count"], 1)
            self.assertEqual(received_cookies_cache["userAgent"], "Mozilla/5.0 TestAgent")

            # 4. Uji Live Log Console di GUI
            win.append_log("INFO", "Pesan info pengujian")
            win.append_log("ERROR", "Pesan error pengujian lengkap")
            console_text = win.log_console.toPlainText()
            self.assertIn("Pesan info pengujian", console_text)
            self.assertIn("Pesan error pengujian lengkap", console_text)
        finally:
            win.close()

    def test_live_multisite_extraction(self):
        # Uji langsung ekstraksi info pada Bilibili.com (dengan patch 412), Bilibili.tv, dan YouTube
        test_urls = [
            ("Bilibili Mainland", "https://www.bilibili.com/video/BV1cdpc6PErN/"),
            ("Bilibili Intl", "https://www.bilibili.tv/en/video/4797844121458181"),
            ("YouTube", "https://www.youtube.com/watch?v=lCJvkQdYA_c"),
        ]
        for name, url in test_urls:
            info = self.downloader.get_video_info(url)
            self.assertTrue(bool(info.get("title")), f"Info judul dari {name} ({url}) harus berhasil diambil")
            self.assertGreater(info.get("formats_count", 0), 0, f"Jumlah format {name} harus > 0")
            print(f"[PASS] {name}: {info.get('title')} ({info.get('formats_count')} formats)")


if __name__ == '__main__':
    unittest.main()
