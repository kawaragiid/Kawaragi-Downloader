def get_format_options(format_type: str) -> str:
    """
    Strategi Anti-Gagal:
    Selalu ambil kualitas video dan audio terbaik yang tersedia (bestvideo+bestaudio).
    Jika terpisah, yt-dlp akan menggabungkannya.
    Jika tidak ada format gabungan, ambil format tunggal terbaik (/best).
    """
    return "bestvideo+bestaudio/best"