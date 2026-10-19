import os
import re
import glob
import traceback

# Aktifkan kompatibilitas curl_cffi 0.15+ sebelum yt_dlp di-import agar TLS Impersonation aktif
try:
    import curl_cffi
    if hasattr(curl_cffi, "__version__") and not curl_cffi.__version__.startswith(("0.5.10", "0.10", "0.11", "0.12", "0.13", "0.14")):
        curl_cffi.__version__ = "0.14.0"
except Exception:
    pass

import yt_dlp
from app.utils.file_utils import get_ffmpeg_path, format_bytes, format_seconds
from app.utils.log_utils import setup_logger

logger = setup_logger("downloader", "downloader.log")

# Patch Bilibili extractor agar otomatis fallback jika terkena HTTP Error 412 pada endpoint WBI
try:
    from yt_dlp.extractor.bilibili import BilibiliBaseIE
    if not getattr(BilibiliBaseIE, "_kawaragi_patched", False):
        _orig_bilibili_playinfo = BilibiliBaseIE._download_playinfo

        def _patched_bilibili_playinfo(self, bvid, cid, headers=None, query=None):
            try:
                return _orig_bilibili_playinfo(self, bvid, cid, headers=headers, query=query)
            except Exception as e:
                logger.warning(f"Bilibili WBI playurl gagal ({e}), beralih ke fallback endpoint playurl...")
                params = {'bvid': bvid, 'cid': cid, 'fnval': 4048, 'fourk': 1, **(query or {})}
                if self.is_logged_in:
                    params.pop('try_look', None)
                else:
                    params.setdefault('try_look', 1)
                req_headers = dict(self._HEADERS)
                if headers:
                    req_headers.update(headers)
                return self._download_json(
                    'https://api.bilibili.com/x/player/playurl', bvid,
                    query=params, headers=req_headers,
                    note=f'Downloading video formats (fallback) for cid {cid}'
                )['data']

        BilibiliBaseIE._download_playinfo = _patched_bilibili_playinfo
        BilibiliBaseIE._kawaragi_patched = True
except Exception as e:
    logger.warning(f"Gagal memasang patch Bilibili: {e}")


VALID_BROWSERS = {"chrome", "edge", "firefox", "brave", "opera", "vivaldi", "chromium", "safari"}


def clean_error_message(text: str) -> str:
    """Membersihkan kode warna terminal (ANSI) dari pesan error."""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', str(text))


class DownloadCancelledException(Exception):
    """Exception khusus saat unduhan dibatalkan oleh user."""
    pass


class YtdlpGuiLogger:
    """Logger kustom untuk menangkap semua output internal yt-dlp ke GUI dan file log."""
    def __init__(self, log_callback=None):
        self.log_callback = log_callback

    def debug(self, msg):
        clean = clean_error_message(msg)
        # Filter baris progres mentah agar tidak membanjiri log
        if clean.startswith("[download]") and ("ETA" in clean or "%" in clean):
            return
        logger.info(clean)
        if self.log_callback:
            self.log_callback("INFO", clean)

    def info(self, msg):
        clean = clean_error_message(msg)
        logger.info(clean)
        if self.log_callback:
            self.log_callback("INFO", clean)

    def warning(self, msg):
        clean = clean_error_message(msg)
        logger.warning(clean)
        if self.log_callback:
            self.log_callback("WARNING", f"⚠️ {clean}")

    def error(self, msg):
        clean = clean_error_message(msg)
        logger.error(clean)
        if self.log_callback:
            self.log_callback("ERROR", f"❌ {clean}")


class Downloader:
    def __init__(self, progress_callback=None, completion_callback=None, error_callback=None, log_callback=None):
        self.progress_callback = progress_callback
        self.completion_callback = completion_callback
        self.error_callback = error_callback
        self.log_callback = log_callback
        self.is_cancelled = False
        self.ffmpeg_path = get_ffmpeg_path()

    def _emit_log(self, level: str, message: str):
        logger.info(f"[{level}] {message}")
        if self.log_callback:
            self.log_callback(level, message)

    def cancel(self):
        """Meminta pembatalan proses download."""
        self.is_cancelled = True
        self._emit_log("WARNING", "Permintaan pembatalan diterima. Menghentikan proses...")

    def _apply_cookie_options(self, ydl_opts: dict, browser_cookie: str, custom_user_agent: str = ""):
        """Mengatur opsi autentikasi cookies secara aman tanpa memicu error unsupported browser."""
        if custom_user_agent:
            ydl_opts.setdefault('http_headers', {})['User-Agent'] = custom_user_agent

        if not browser_cookie or browser_cookie in ("Tanpa Login", "none", "auto"):
            return

        if browser_cookie.lower().endswith('.txt'):
            if os.path.isfile(browser_cookie) and os.path.getsize(browser_cookie) > 0:
                ydl_opts['cookiefile'] = browser_cookie
                self._emit_log("INFO", f"Menggunakan file cookies: {browser_cookie}")
            else:
                self._emit_log("WARNING", f"File cookies tidak ditemukan atau kosong ({browser_cookie}), melanjutkan tanpa cookies.")
        elif browser_cookie.lower() in VALID_BROWSERS:
            ydl_opts['cookiesfrombrowser'] = (browser_cookie.lower(),)
            self._emit_log("INFO", f"Mengambil cookies langsung dari browser: {browser_cookie}")
        else:
            self._emit_log("WARNING", f"Sumber cookies '{browser_cookie}' tidak dikenali, melanjutkan tanpa cookies.")

    def _build_base_opts(self, browser_cookie: str = "Tanpa Login", custom_user_agent: str = "") -> dict:
        ydl_opts = {
            'quiet': False,
            'no_warnings': False,
            'nocheckcertificate': True,
            'geo_bypass': True,
            'noplaylist': True,
            'retries': 5,
            'fragment_retries': 5,
            'windowsfilenames': True,
            'logger': YtdlpGuiLogger(self.log_callback),
        }

        # Aktifkan impersonation Chrome otomatis via curl_cffi jika tersedia untuk menembus proteksi Cloudflare/TikTok/dll
        try:
            from yt_dlp.networking.impersonate import ImpersonateTarget
            ydl_opts['impersonate'] = ImpersonateTarget.from_str('chrome')
        except Exception:
            pass

        self._apply_cookie_options(ydl_opts, browser_cookie, custom_user_agent)
        return ydl_opts

    def get_video_info(self, url: str, browser_cookie: str = "Tanpa Login", custom_user_agent: str = "") -> dict:
        self._emit_log("INFO", f"🔍 Memulai analisis tautan: {url}")
        self._emit_log("INFO", f"🔧 FFmpeg terdeteksi di: {self.ffmpeg_path}")

        attempts = [
            {"label": "Mode Utama (Cookies + Impersonasi)", "cookie": browser_cookie, "use_impersonate": True},
        ]
        # Jika memakai cookies dan gagal (misal DB Chrome terkunci atau cookies kadaluarsa), coba fallback tanpa cookies
        if browser_cookie and browser_cookie not in ("Tanpa Login", "none", "auto"):
            attempts.append({"label": "Mode Fallback (Tanpa Cookies)", "cookie": "Tanpa Login", "use_impersonate": True})
        attempts.append({"label": "Mode Standar Kompatibilitas", "cookie": "Tanpa Login", "use_impersonate": False})

        last_error = ""
        for idx, att in enumerate(attempts, 1):
            ydl_opts = self._build_base_opts(att["cookie"], custom_user_agent)
            if not att["use_impersonate"]:
                ydl_opts.pop('impersonate', None)

            try:
                if idx > 1:
                    self._emit_log("WARNING", f"🔄 Mencoba {att['label']} (Percobaan {idx}/{len(attempts)})...")
                with yt_dlp.YoutubeDL(ydl_opts) as ydl: # type: ignore
                    info = ydl.extract_info(url, download=False)
                    if not info:
                        continue

                    # Jika playlist/multi_video (seperti beberapa video Bilibili atau carousel Instagram/TikTok)
                    if 'entries' in info and info['entries']:
                        entries = [e for e in info['entries'] if e]
                        if entries:
                            first_entry = entries[0]
                            title = info.get("title") or first_entry.get("title", "Tidak ada judul")
                            duration = info.get("duration") or first_entry.get("duration") or 0
                            uploader = info.get("uploader") or first_entry.get("uploader", "Tidak diketahui")
                            thumbnail = info.get("thumbnail") or first_entry.get("thumbnail", "")
                        else:
                            title = info.get("title", "Tidak ada judul")
                            duration = info.get("duration", 0) or 0
                            uploader = info.get("uploader", "Tidak diketahui")
                            thumbnail = info.get("thumbnail", "")
                    else:
                        title = info.get("title", "Tidak ada judul")
                        duration = info.get("duration", 0) or 0
                        uploader = info.get("uploader", "Tidak diketahui")
                        thumbnail = info.get("thumbnail", "")

                    available_subs = set()
                    if 'subtitles' in info and info['subtitles']:
                        available_subs.update(info['subtitles'].keys())
                    if 'automatic_captions' in info and info['automatic_captions']:
                        available_subs.update(info['automatic_captions'].keys())

                    sorted_subs = sorted(list(available_subs))
                    priority_subs = []
                    for lang in ['id', 'en', 'en-US', 'ja', 'ko', 'zh']:
                        if lang in sorted_subs:
                            priority_subs.append(lang)
                            sorted_subs.remove(lang)
                    final_subs = priority_subs + sorted_subs

                    extractor_name = info.get("extractor_key") or info.get("extractor") or "Universal"
                    formats_count = len(info.get("formats", []))
                    self._emit_log("SUCCESS", f"✅ Berhasil memuat info [{extractor_name}]: '{title}' ({formats_count} format tersedia)")

                    return {
                        "title": title,
                        "duration": duration,
                        "uploader": uploader,
                        "thumbnail": thumbnail,
                        "subtitles": final_subs,
                        "extractor": extractor_name,
                        "formats_count": formats_count,
                        "webpage_url": info.get("webpage_url", url)
                    }
            except Exception as e:
                clean_msg = clean_error_message(str(e))
                tb_str = traceback.format_exc()
                last_error = clean_msg
                logger.error(f"Error info video ({att['label']}): {clean_msg}\n{tb_str}")
                self._emit_log("ERROR", f"Gagal pada {att['label']}: {clean_msg}")

        if self.error_callback:
            self.error_callback(last_error or "Gagal mengambil informasi video.")
        return {}

    def _get_format_string(self, quality: str) -> str:
        """
        Menghasilkan format selector yt-dlp yang mendukung baik video horizontal (1920x1080)
        maupun video vertikal/portrait seperti TikTok/Shorts/Reels (1080x1920),
        serta memiliki fallback ke best agar tidak pernah gagal dengan 'Requested format is not available'.
        """
        if quality == "1080p":
            return "bv*[height<=1080]+ba/bv*[width<=1080]+ba/b[height<=1080]/b[width<=1080]/bv*+ba/b"
        elif quality == "720p":
            return "bv*[height<=720]+ba/bv*[width<=720]+ba/b[height<=720]/b[width<=720]/bv*+ba/b"
        elif quality == "480p":
            return "bv*[height<=480]+ba/bv*[width<=480]+ba/b[height<=480]/b[width<=480]/bv*+ba/b"
        elif quality == "360p":
            return "bv*[height<=360]+ba/bv*[width<=360]+ba/b[height<=360]/b[width<=360]/bv*+ba/b"
        elif quality in ("audio_320", "audio_192"):
            return "ba/b"
        elif quality == "audio_m4a":
            return "ba[ext=m4a]/ba/b"
        else:
            return "bv*+ba/b"

    def download(self, url: str, quality: str = "best", include_subtitles: bool = False,
                 subtitle_language: str = "en", subtitle_format: str = "srt",
                 include_thumbnail: bool = False, thumbnail_format: str = "jpg",
                 out_dir: str = "", browser_cookie: str = "Tanpa Login",
                 target_format: str = "Otomatis", custom_user_agent: str = ""):

        self.is_cancelled = False
        if not out_dir:
            out_dir = os.getcwd()
        os.makedirs(out_dir, exist_ok=True)

        def progress_hook(d):
            if self.is_cancelled:
                raise DownloadCancelledException("Unduhan dibatalkan oleh pengguna.")

            if d['status'] == 'downloading':
                downloaded = d.get('downloaded_bytes', 0)
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                speed = d.get('speed', 0)
                eta = d.get('eta', 0)

                if total and total > 0:
                    percent_val = int(min(100, (downloaded / total) * 100))
                else:
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
                filename = os.path.basename(d.get('filename', ''))
                self._emit_log("INFO", f"📦 Stream selesai diunduh: {filename}. Menjalankan post-processing FFmpeg...")
                if self.progress_callback:
                    self.progress_callback({
                        "percent": 99,
                        "speed": "--",
                        "eta": "00:00",
                        "downloaded": "Selesai",
                        "total": "Selesai",
                        "status": "Memproses / menggabungkan file dengan FFmpeg..."
                    })

        is_audio_only = quality.startswith("audio")
        format_str = self._get_format_string(quality)

        attempts = [
            {"label": "Strategi Utama", "cookie": browser_cookie, "fmt": format_str},
        ]
        if browser_cookie and browser_cookie not in ("Tanpa Login", "none", "auto"):
            attempts.append({"label": "Strategi Fallback (Tanpa Cookies)", "cookie": "Tanpa Login", "fmt": format_str})
        if format_str != "bv*+ba/b":
            attempts.append({"label": "Strategi Format Universal (Best)", "cookie": "Tanpa Login", "fmt": "bv*+ba/b"})

        last_error = ""
        for idx, att in enumerate(attempts, 1):
            if self.is_cancelled:
                break

            postprocessors = []
            if quality == "audio_320":
                postprocessors.append({
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '320',
                })
            elif quality == "audio_192":
                postprocessors.append({
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                })
            elif quality == "audio_m4a":
                postprocessors.append({
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'm4a',
                })

            ydl_opts = self._build_base_opts(att["cookie"], custom_user_agent)
            ydl_opts.update({
                'format': att["fmt"],
                'outtmpl': os.path.join(out_dir, '%(title).180B.%(ext)s'),
                'progress_hooks': [progress_hook],
                'concurrent_fragment_downloads': 4,
            })

            if include_subtitles and subtitle_language and subtitle_language != "Tidak ada":
                ydl_opts['writesubtitles'] = True
                ydl_opts['writeautomaticsub'] = True
                ydl_opts['subtitleslangs'] = [subtitle_language]
                if subtitle_format:
                    ydl_opts['subtitlesformat'] = subtitle_format
                    postprocessors.append({
                        'key': 'FFmpegSubtitlesConvertor',
                        'format': subtitle_format,
                    })

            if include_thumbnail:
                ydl_opts['writethumbnail'] = True
                if thumbnail_format:
                    postprocessors.append({
                        'key': 'FFmpegThumbnailsConvertor',
                        'format': thumbnail_format,
                        'when': 'before_dl'
                    })

            if postprocessors:
                ydl_opts['postprocessors'] = postprocessors

            try:
                self._emit_log("INFO", f"🚀 Memulai unduhan [{att['label']}]: {url} (Kualitas: {quality}, Format Selector: {att['fmt']})")
                with yt_dlp.YoutubeDL(ydl_opts) as ydl: # type: ignore
                    info = ydl.extract_info(url, download=True)

                    # Jika multi_video / playlist, ambil entri pertama untuk nama file
                    target_info = info
                    if 'entries' in info and info['entries']:
                        entries = [e for e in info['entries'] if e]
                        if entries:
                            target_info = entries[0]

                    final_filename = ydl.prepare_filename(target_info)
                    base = os.path.splitext(final_filename)[0]
                    downloaded_file = final_filename

                    # Cek dari requested_downloads jika ada filepath aktual
                    req_dls = target_info.get('requested_downloads') or info.get('requested_downloads') or []
                    for rd in req_dls:
                        fp = rd.get('filepath')
                        if fp and os.path.exists(fp):
                            downloaded_file = fp
                            break

                    if not os.path.exists(downloaded_file):
                        expected_exts = ['.mp3', '.m4a', '.aac', '.opus', '.webm'] if is_audio_only else ['.mp4', '.mkv', '.webm', '.ts', '.mov', '.flv']
                        for ext in expected_exts:
                            if os.path.exists(base + ext):
                                downloaded_file = base + ext
                                break

                    if not os.path.exists(downloaded_file):
                        matched = glob.glob(f"{glob.escape(base)}*")
                        if matched:
                            media_files = [m for m in matched if not m.endswith(('.vtt', '.srt', '.ass', '.jpg', '.png', '.webp', '.part', '.ytdl'))]
                            downloaded_file = media_files[0] if media_files else matched[0]

                    self._emit_log("SUCCESS", f"🎉 File berhasil diunduh ke: {downloaded_file}")
                    if self.completion_callback:
                        self.completion_callback(downloaded_file)
                    return

            except DownloadCancelledException:
                logger.info("Download dibatalkan oleh pengguna.")
                self._emit_log("WARNING", "⏹ Unduhan telah dibatalkan oleh pengguna.")
                if self.error_callback:
                    self.error_callback("Unduhan dibatalkan.")
                return
            except Exception as e:
                clean_msg = clean_error_message(str(e))
                tb_str = traceback.format_exc()
                last_error = clean_msg
                logger.error(f"Error download ({att['label']}): {clean_msg}\n{tb_str}")
                self._emit_log("ERROR", f"Gagal pada {att['label']}: {clean_msg}")
                self._emit_log("ERROR", f"Detail Traceback:\n{tb_str}")

        if self.error_callback:
            self.error_callback(last_error or "Gagal mengunduh video.")