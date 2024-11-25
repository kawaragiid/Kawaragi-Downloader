def get_format_options(format_type: str) -> dict:
    """Mengembalikan opsi format untuk yt-dlp berdasarkan jenis format."""
    options = {
        "video_mp4": "bestvideo[ext=mp4]+bestaudio/best[ext=mp4]",
        "video_webm": "bestvideo[ext=webm]+bestaudio/best[ext=webm]",
        "audio_mp3": "bestaudio/best",
        "audio_aac": "bestaudio[ext=m4a]/best[ext=m4a]",
    }
    return options.get(format_type, "best")
