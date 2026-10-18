import os
import sys
import shutil

def get_base_dir():
    """Mendapatkan direktori dasar aplikasi baik saat running script maupun binary/frozen."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

def get_ffmpeg_path() -> str:
    """
    Mendeteksi path ffmpeg secara otomatis dengan urutan prioritas:
    1. Folder aplikasi/executable (sys.executable)
    2. Folder PyInstaller extraction (_MEIPASS)
    3. Root folder proyek
    4. System PATH
    """
    candidates = []
    
    # 1. Folder exe
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        candidates.append(os.path.join(exe_dir, "ffmpeg.exe"))
        candidates.append(os.path.join(exe_dir, "_internal", "ffmpeg.exe"))
        
    # 2. _MEIPASS jika onefile
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        candidates.append(os.path.join(meipass, "ffmpeg.exe"))
        candidates.append(os.path.join(meipass, "assets", "ffmpeg.exe"))
        
    # 3. Root folder proyek
    root_dir = get_base_dir()
    candidates.append(os.path.join(root_dir, "ffmpeg.exe"))
    candidates.append(os.path.join(root_dir, "ffmpeg"))
    
    for path in candidates:
        if os.path.isfile(path) and os.access(path, os.X_OK if os.name != 'nt' else os.R_OK):
            return os.path.abspath(path)
            
    # 4. Cari di System PATH
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg
        
    # Fallback default
    return "ffmpeg"

def ensure_directory_exists(directory: str):
    """Memastikan direktori ada, jika belum maka dibuat."""
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)

def format_bytes(bytes_num: float) -> str:
    """Format bytes ke format yang mudah dibaca (KB, MB, GB)."""
    if not bytes_num or bytes_num <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    unit_index = 0
    size = float(bytes_num)
    while size >= 1024.0 and unit_index < len(units) - 1:
        size /= 1024.0
        unit_index += 1
    return f"{size:.2f} {units[unit_index]}"

def format_seconds(seconds_num: float) -> str:
    """Format detik ke format MM:SS atau HH:MM:SS."""
    if not seconds_num or seconds_num <= 0:
        return "00:00"
    seconds = int(seconds_num)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"
