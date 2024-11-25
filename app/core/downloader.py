import yt_dlp
import os
from app.core.subtitle_handler import SubtitleHandler
from app.core.thumbnail_handler import ThumbnailHandler
from app.utils.format_utils import get_format_options
from app.utils.log_utils import setup_logger

logger = setup_logger("downloader", "downloader.log")

class Downloader:
    def __init__(self, progress_bar=None, completion_callback=None):
        """Inisialisasi downloader dengan progress bar dan callback opsional."""
        self.progress_bar = progress_bar
        self.completion_callback = completion_callback

    def get_video_info(self, url: str) -> dict:
        """Mengambil informasi video seperti judul, durasi, dan subtitle."""
        try:
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(url, download=False)
                title = info.get("title", "Tidak tersedia")
                duration = info.get("duration", 0)
                subtitles = list(info.get("subtitles", {}).keys())
                return {"title": title, "duration": duration, "subtitles": subtitles}
        except Exception as e:
            logger.error(f"Error saat mengambil info video: {e}")
            return {}

    def download(self, url: str, format_type: str, include_subtitles: bool, subtitle_language: str, subtitle_format: str, include_thumbnail: bool, thumbnail_format: str, output_directory: str):
        """Mengunduh video/audio, subtitle, dan thumbnail."""
        if not os.path.exists(output_directory):
            os.makedirs(output_directory)

        def progress_hook(d):
            if d['status'] == 'downloading' and self.progress_bar:
                percent = float(d.get('percent', 0))
                self.progress_bar.setValue(int(percent))
            if d['status'] == 'finished':
                filename = d['filename']
                logger.info(f"Unduhan selesai: {filename}")

                # Konversi subtitle jika diperlukan
                if include_subtitles:
                    SubtitleHandler.convert_subtitle(filename, subtitle_format)

                # Konversi thumbnail jika diperlukan
                if include_thumbnail:
                    thumbnail_file = f"{os.path.splitext(filename)[0]}-thumbnail.jpg"
                    ThumbnailHandler.convert_thumbnail(thumbnail_file, thumbnail_format)

        ydl_opts = {
            'format': get_format_options(format_type) if format_type else 'bestvideo+bestaudio/best',
            'outtmpl': os.path.join(output_directory, '%(title)s.%(ext)s'),
            'writesubtitles': include_subtitles,
            'subtitleslangs': [subtitle_language] if include_subtitles else None,
            'writethumbnail': include_thumbnail,
            'progress_hooks': [progress_hook],
            'sanitize_filename': True,
        }

        try:
            logger.info(f"Memulai unduhan: {url}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            if self.completion_callback:
                self.completion_callback()
            logger.info("Unduhan selesai.")
        except Exception as e:
            logger.error(f"Error saat mengunduh: {e}")
            if self.progress_bar:
                self.progress_bar.setValue(0)
