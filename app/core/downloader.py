import yt_dlp
import os
import re
import glob
from app.utils.file_utils import get_ffmpeg_path, format_bytes, format_seconds
from app.utils.log_utils import setup_logger

logger = setup_logger("downloader", "downloader.log")

def clean_error_message(text: str) -> str:
    """Membersihkan kode warna terminal (ANSI) dari pesan error."""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

class DownloadCancelledException(Exception):
    """Exception khusus saat unduhan dibatalkan oleh user."""
    pass

class Downloader:
    def __init__(self, progress_callback=None, completion_callback=None, error_callback=None):
        self.progress_callback = progress_callback
        self.completion_callback = completion_callback
        self.error_callback = error_callback
        self.is_cancelled = False
        self.ffmpeg_path = get_ffmpeg_path()

    def cancel(self):
        """Meminta pembatalan proses download."""
        self.is_cancelled = True

    def get_video_info(self, url: str, browser_cookie: str = "Tanpa Login") -> dict:
        ydl_opts = {
            'quiet': True, 
            'no_warnings': True,
            'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
            'nocheckcertificate': True,
            'noplaylist': True,
        }
        
        if self.ffmpeg_path and os.path.exists(self.ffmpeg_path):
            ydl_opts['ffmpeg_location'] = os.path.dirname(self.ffmpeg_path)

        if browser_cookie and browser_cookie != "Tanpa Login":
            if browser_cookie.endswith('.txt') and os.path.exists(browser_cookie):
                ydl_opts['cookiefile'] = browser_cookie
            else:
                ydl_opts['cookiesfrombrowser'] = (browser_cookie.lower(),) # type: ignore

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl: # type: ignore
                info = ydl.extract_info(url, download=False)
                if not info:
                    return {}
                
                # Kumpulkan subtitle manual & otomatis
                available_subs = set()
                if 'subtitles' in info and info['subtitles']:
                    available_subs.update(info['subtitles'].keys())
                if 'automatic_captions' in info and info['automatic_captions']:
                    available_subs.update(info['automatic_captions'].keys())
                    
                sorted_subs = sorted(list(available_subs))
                # Prioritaskan bahasa Indonesia dan Inggris di awal jika ada
                priority_subs = []
                for lang in ['id', 'en', 'en-US', 'ja', 'ko', 'zh']:
                    if lang in sorted_subs:
                        priority_subs.append(lang)
                        sorted_subs.remove(lang)
                final_subs = priority_subs + sorted_subs

                return {
                    "title": info.get("title", "Tidak ada judul"),
                    "duration": info.get("duration", 0) or 0,
                    "uploader": info.get("uploader", "Tidak diketahui"),
                    "thumbnail": info.get("thumbnail", ""),
                    "subtitles": final_subs,
                    "webpage_url": info.get("webpage_url", url)
                }
        except Exception as e:
            clean_msg = clean_error_message(str(e))
            logger.error(f"Error info video: {clean_msg}")
            if self.error_callback:
                self.error_callback(clean_msg)
            return {}

    def download(self, url: str, quality: str = "best", include_subtitles: bool = False, 
                 subtitle_language: str = "en", subtitle_format: str = "srt", 
                 include_thumbnail: bool = False, thumbnail_format: str = "jpg", 
                 out_dir: str = "", browser_cookie: str = "Tanpa Login",
                 target_format: str = "Otomatis"):
        
        self.is_cancelled = False
        if not out_dir:
            out_dir = os.getcwd()
        os.makedirs(out_dir, exist_ok=True)

        # Hook progress interaktif
        def progress_hook(d):
            if self.is_cancelled:
                raise DownloadCancelledException("Unduhan dibatalkan.")
                
            if d['status'] == 'downloading':
                downloaded = d.get('downloaded_bytes', 0)
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                speed = d.get('speed', 0)
                eta = d.get('eta', 0)
                
                p_str = d.get('_percent_str', '0%').replace('%', '').strip()
                clean_p_str = ''.join(c for c in p_str if c.isdigit() or c == '.')
                try:
                    percent_val = int(float(clean_p_str))
                except Exception:
                    percent_val = 0

                speed_str = f"{format_bytes(speed)}/s" if speed else "-- KB/s"
                eta_str = format_seconds(eta) if eta else "--:--"
                downloaded_str = format_bytes(downloaded)
                total_str = format_bytes(total) if total else "--"

                progress_data = {
                    "percent": percent_val,
                    "speed": speed_str,
                    "eta": eta_str,
                    "downloaded": downloaded_str,
                    "total": total_str,
                    "status": f"Mengunduh... {downloaded_str} / {total_str} ({speed_str})"
                }
                
                if self.progress_callback:
                    self.progress_callback(progress_data)
                    
            elif d['status'] == 'finished':
                if self.progress_callback:
                    self.progress_callback({
                        "percent": 99,
                        "speed": "",
                        "eta": "",
                        "downloaded": "",
                        "total": "",
                        "status": "Memproses / menggabungkan file dengan FFmpeg..."
                    })

        # Konfigurasi format unduhan berdasarkan pilihan kualitas
        is_audio_only = quality.startswith("audio")
        postprocessors = []

        if quality == "1080p":
            format_str = "bv*[height<=1080]+ba/b[height<=1080]/best"
        elif quality == "720p":
            format_str = "bv*[height<=720]+ba/b[height<=720]/best"
        elif quality == "480p":
            format_str = "bv*[height<=480]+ba/b[height<=480]/best"
        elif quality == "360p":
            format_str = "bv*[height<=360]+ba/b[height<=360]/best"
        elif quality == "audio_320":
            format_str = "ba/b"
            postprocessors.append({
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320',
            })
        elif quality == "audio_192":
            format_str = "ba/b"
            postprocessors.append({
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            })
        elif quality == "audio_m4a":
            format_str = "ba[ext=m4a]/ba/b"
            postprocessors.append({
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'm4a',
            })
        else:
            # Default / Best
            format_str = "bv*+ba/b"

        ydl_opts = {
            'format': format_str,
            'outtmpl': os.path.join(out_dir, '%(title)s.%(ext)s'),
            'progress_hooks': [progress_hook],
            'sanitize_filename': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            'noplaylist': True,
            'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
        }

        # Lokasi FFmpeg
        if self.ffmpeg_path and os.path.exists(self.ffmpeg_path):
            ydl_opts['ffmpeg_location'] = os.path.dirname(self.ffmpeg_path)

        # Pengaturan Subtitle
        if include_subtitles and subtitle_language:
            ydl_opts['writesubtitles'] = True
            ydl_opts['writeautomaticsub'] = True
            ydl_opts['subtitleslangs'] = [subtitle_language]
            if subtitle_format:
                ydl_opts['subtitlesformat'] = subtitle_format
                postprocessors.append({
                    'key': 'FFmpegSubtitlesConvertor',
                    'format': subtitle_format,
                })

        # Pengaturan Thumbnail
        if include_thumbnail:
            ydl_opts['writethumbnail'] = True
            if thumbnail_format:
                postprocessors.append({
                    'key': 'FFmpegThumbnailsConvertor',
                    'format': thumbnail_format,
                    'when': 'before_dl'
                })

        # Tambahkan postprocessors jika ada
        if postprocessors:
            ydl_opts['postprocessors'] = postprocessors

        # Cookies
        if browser_cookie and browser_cookie != "Tanpa Login":
            if browser_cookie.endswith('.txt') and os.path.exists(browser_cookie):
                ydl_opts['cookiefile'] = browser_cookie
            else:
                ydl_opts['cookiesfrombrowser'] = (browser_cookie.lower(),) # type: ignore

        try:
            logger.info(f"Memulai download: {url} (Kualitas: {quality})")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl: # type: ignore
                info = ydl.extract_info(url, download=True)
                final_filename = ydl.prepare_filename(info)
                
                # Deteksi file fisik hasil akhir
                base = os.path.splitext(final_filename)[0]
                downloaded_file = final_filename

                # Cek variasi ekstensi setelah FFmpeg post-processing
                expected_exts = []
                if is_audio_only:
                    expected_exts = ['.mp3', '.m4a', '.aac', '.opus', '.webm']
                else:
                    expected_exts = ['.mp4', '.mkv', '.webm', '.ts', '.mov']
                
                for ext in expected_exts:
                    if os.path.exists(base + ext):
                        downloaded_file = base + ext
                        break

                if not os.path.exists(downloaded_file):
                    # Cari file yang berawalan nama base di folder tujuan
                    matched = glob.glob(f"{glob.escape(base)}.*")
                    if matched:
                        # Ambil yang bukan subtitle (.vtt/.srt) dan bukan thumbnail (.jpg/.webp) jika mencari video/audio
                        media_files = [m for m in matched if not m.endswith(('.vtt', '.srt', '.ass', '.jpg', '.png', '.webp'))]
                        if media_files:
                            downloaded_file = media_files[0]
                        else:
                            downloaded_file = matched[0]

                if self.completion_callback:
                    self.completion_callback(downloaded_file)
                    
        except DownloadCancelledException:
            logger.info("Download dibatalkan oleh pengguna.")
            if self.error_callback:
                self.error_callback("Unduhan dibatalkan.")
        except Exception as e:
            clean_msg = clean_error_message(str(e))
            logger.error(f"Error download: {clean_msg}")
            if self.error_callback:
                self.error_callback(clean_msg)