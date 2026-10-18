import unittest
import os
import shutil
from app.core.downloader import Downloader
from app.utils.validation import is_valid_url
from app.utils.file_utils import get_ffmpeg_path, format_bytes, format_seconds
from app.core.config import Config

class TestDownloader(unittest.TestCase):
    def setUp(self):
        self.downloader = Downloader()

    def test_valid_url(self):
        valid_urls = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "http://youtu.be/dQw4w9WgXcQ",
            "https://tiktok.com/@user/video/123456",
            "https://instagram.com/p/abcdef"
        ]
        invalid_urls = [
            "invalid_url",
            "ftp://bad",
            "",
            "notaurl"
        ]
        for url in valid_urls:
            self.assertTrue(is_valid_url(url), f"Should be valid: {url}")
        for url in invalid_urls:
            self.assertFalse(is_valid_url(url), f"Should be invalid: {url}")

    def test_ffmpeg_detection(self):
        ffmpeg_path = get_ffmpeg_path()
        self.assertTrue(bool(ffmpeg_path))
        # Pastikan terdeteksi (baik file ffmpeg.exe di root atau sistem)
        print("Detected FFmpeg:", ffmpeg_path)

    def test_format_helpers(self):
        self.assertEqual(format_bytes(1024), "1.00 KB")
        self.assertEqual(format_bytes(1024 * 1024 * 5), "5.00 MB")
        self.assertEqual(format_seconds(65), "01:05")
        self.assertEqual(format_seconds(3665), "01:01:05")

    def test_config_history(self):
        test_entry = {
            "title": "Test Video",
            "url": "https://example.com/video",
            "file_path": "C:\\fake\\video.mp4"
        }
        Config.save_history_entry(test_entry)
        history = Config.load_history()
        self.assertTrue(any(item.get("title") == "Test Video" for item in history))

if __name__ == '__main__':
    unittest.main()
