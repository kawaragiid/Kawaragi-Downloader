import os
import sys
import shutil

def get_base_dir() -> str:
    """Mendapatkan direktori dasar aplikasi baik saat running script maupun binary/frozen."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

def get_extension_dir() -> str:
    """Mendapatkan path absolut ke folder ekstensi Kawaragi-Trigger."""
    candidates = []
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        candidates.append(os.path.join(exe_dir, "Kawaragi-Trigger"))
        candidates.append(os.path.join(exe_dir, "_internal", "Kawaragi-Trigger"))
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        candidates.append(os.path.join(meipass, "Kawaragi-Trigger"))
    candidates.append(os.path.join(get_base_dir(), "Kawaragi-Trigger"))
    candidates.append(os.path.abspath("Kawaragi-Trigger"))

    for path in candidates:
        if os.path.isdir(path) and os.path.isfile(os.path.join(path, "manifest.json")):
            return os.path.abspath(path)
    return os.path.join(get_base_dir(), "Kawaragi-Trigger")

def get_ffmpeg_path() -> str:
    """
    Mendeteksi path ffmpeg secara otomatis dan mendaftarkan direktorinya ke PATH
    agar yt-dlp dapat menemukan baik ffmpeg maupun ffprobe.
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
        
    # 3. Root folder proyek & C:\ffmpeg\bin
    root_dir = get_base_dir()
    candidates.append(os.path.join(root_dir, "ffmpeg.exe"))
    candidates.append(os.path.join(root_dir, "ffmpeg"))
    candidates.append(r"C:\ffmpeg\bin\ffmpeg.exe")
    
    detected_ffmpeg = None
    for path in candidates:
        if os.path.isfile(path) and os.access(path, os.X_OK if os.name != 'nt' else os.R_OK):
            detected_ffmpeg = os.path.abspath(path)
            break
            
    if not detected_ffmpeg:
        system_ffmpeg = shutil.which("ffmpeg")
        if system_ffmpeg:
            detected_ffmpeg = os.path.abspath(system_ffmpeg)

    # Tambahkan direktori ffmpeg dan C:\ffmpeg\bin ke os.environ["PATH"] agar ffprobe juga ditemukan
    extra_Dirs = []
    if detected_ffmpeg and os.path.isfile(detected_ffmpeg):
        extra_Dirs.append(os.path.dirname(detected_ffmpeg))
    if os.path.isdir(r"C:\ffmpeg\bin"):
        extra_Dirs.append(r"C:\ffmpeg\bin")

    current_path = os.environ.get("PATH", "")
    for d in extra_Dirs:
        if d.lower() not in current_path.lower():
            current_path = f"{d}{os.pathsep}{current_path}"
    os.environ["PATH"] = current_path

    return detected_ffmpeg or "ffmpeg"

def find_browser_executable(browser: str = "chrome") -> str:
    """Mencari path executable browser (chrome, edge, brave) di Windows."""
    local_app = os.getenv("LOCALAPPDATA", "")
    prog_files = os.getenv("PROGRAMFILES", r"C:\Program Files")
    prog_x86 = os.getenv("PROGRAMFILES(X86)", r"C:\Program Files (x86)")

    paths = {
        "chrome": [
            os.path.join(prog_files, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(prog_x86, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(local_app, "Google", "Chrome", "Application", "chrome.exe"),
            shutil.which("chrome") or ""
        ],
        "edge": [
            os.path.join(prog_x86, "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(prog_files, "Microsoft", "Edge", "Application", "msedge.exe"),
            shutil.which("msedge") or ""
        ],
        "brave": [
            os.path.join(prog_files, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            os.path.join(prog_x86, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            os.path.join(local_app, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            shutil.which("brave") or ""
        ]
    }
    for p in paths.get(browser.lower(), []):
        if p and os.path.isfile(p):
            return p
    return ""

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
