import re
import yt_dlp

def is_valid_url(url: str) -> bool:
    """Memvalidasi URL dengan mendukung berbagai situs."""
    # Regex generik untuk memvalidasi URL
    url_regex = re.compile(
        r'^(https?://)?(www\.)?([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}(/.*)?$'
    )
    if not url_regex.match(url):
        return False

    # Memastikan situs didukung oleh yt-dlp
    try:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            return info is not None
    except Exception:
        return False
