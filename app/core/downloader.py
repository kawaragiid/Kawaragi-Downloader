import yt_dlp
import os
import re
import glob
from app.core.subtitle_handler import SubtitleHandler
from app.core.thumbnail_handler import ThumbnailHandler
from app.utils.log_utils import setup_logger

logger = setup_logger("downloader", "downloader.log")

def clean_error_message(text: str) -> str:
    """Membersihkan kode warna terminal (ANSI) dari pesan error."""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

class Downloader:
    def __init__(self, progress_callback=None, completion_callback=None, error_callback=None):
        self.progress_callback = progress_callback
        self.completion_callback = completion_callback
        self.error_callback = error_callback

    def get_video_info(self, url: str, browser_cookie: str = "Tanpa Login") -> dict:
        # KUNCI ANTI-BLOKIR: Hanya gunakan trik player_client bawaan (tanpa impersonate yg butuh library luar)
        ydl_opts = {
            'quiet': True, 
            'no_warnings': True,
            'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
            'nocheckcertificate': True,
        }
        
        if browser_cookie and browser_cookie != "Tanpa Login":
            if browser_cookie.endswith('.txt') and os.path.exists(browser_cookie):
                ydl_opts['cookiefile'] = browser_cookie
            else:
                ydl_opts['cookiesfrombrowser'] = (browser_cookie.lower(),) # type: ignore

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl: # type: ignore
                info = ydl.extract_info(url, download=False)
                if not info: return {}
                return {
                    "title": info.get("title", "Tidak tersedia"),
                    "duration": info.get("duration", 0),
                    "subtitles": list(info.get("subtitles", {}).keys())
                }
        except Exception as e:
            clean_msg = clean_error_message(str(e))
            logger.error(f"Error info video: {clean_msg}")
            if self.error_callback: self.error_callback(clean_msg)
            return {}

    def download(self, url: str, format_type: str, include_subtitles: bool, 
                 subtitle_language: str, subtitle_format: str, 
                 include_thumbnail: bool, thumbnail_format: str, out_dir: str,
                 browser_cookie: str = "Tanpa Login"):
        
        if not os.path.exists(out_dir): os.makedirs(out_dir)

        def progress_hook(d):
            if d['status'] == 'downloading' and self.progress_callback:
                p_str = d.get('_percent_str', '0%').replace('%', '').strip()
                clean_p_str = ''.join(c for c in p_str if c.isdigit() or c == '.')
                try: self.progress_callback(int(float(clean_p_str)))
                except: pass

        # MODE BRUTAL: Ambil kualitas terbaik, abaikan validasi ekstensi awal
        ydl_opts = {
            'format': 'bv*+ba/b', 
            'outtmpl': os.path.join(out_dir, '%(title)s.%(ext)s'),
            'writesubtitles': include_subtitles,
            'subtitleslangs': [subtitle_language] if include_subtitles else None,
            'writethumbnail': include_thumbnail,
            'progress_hooks': [progress_hook],
            'sanitize_filename': True,
            'no_warnings': True,
            'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
            'nocheckcertificate': True,
        }

        if browser_cookie and browser_cookie != "Tanpa Login":
            if browser_cookie.endswith('.txt') and os.path.exists(browser_cookie):
                ydl_opts['cookiefile'] = browser_cookie
            else:
                ydl_opts['cookiesfrombrowser'] = (browser_cookie.lower(),) # type: ignore

        try:
            logger.info(f"Memulai download anti-blokir: {url}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl: # type: ignore
                info = ydl.extract_info(url, download=True)
                final_filename = ydl.prepare_filename(info)
                
                # Deteksi file asli yang terunduh
                base = os.path.splitext(final_filename)[0]
                downloaded_file = final_filename
                
                for ext in ['.mp4', '.mkv', '.webm', '.m4a', '.mp3']:
                    if os.path.exists(base + ext):
                        downloaded_file = base + ext
                        break

                if self.completion_callback:
                    self.completion_callback(downloaded_file)
                    
        except Exception as e:
            clean_msg = clean_error_message(str(e))
            logger.error(f"Error download: {clean_msg}")
            if self.error_callback: self.error_callback(clean_msg)