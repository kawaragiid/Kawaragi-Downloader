import unittest
from app.core.downloader import Downloader
from app.utils.validation import is_valid_url

class TestDownloader(unittest.TestCase):
    def setUp(self):
        self.downloader = Downloader()

    def test_valid_url(self):
        valid_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        invalid_url = "invalid_url"
        self.assertTrue(is_valid_url(valid_url))
        self.assertFalse(is_valid_url(invalid_url))

    def test_download_video_mp4(self):
        self.downloader.download(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            format_type="video_mp4",
            include_subtitles=False,
            include_thumbnail=False
        )
        self.assertTrue(os.path.exists(self.downloader.output_dir))
