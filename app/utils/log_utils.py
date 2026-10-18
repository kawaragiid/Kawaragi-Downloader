import logging
import os

def setup_logger(name: str, log_file: str, level=logging.INFO):
    """Membuat logger yang aman dari UAC Windows dengan menyimpannya di AppData."""
    local_appdata = os.getenv('LOCALAPPDATA')
    if not local_appdata:
        local_appdata = os.path.join(os.path.expanduser('~'), 'AppData', 'Local')
        
    app_data_dir = os.path.join(local_appdata, 'KawaragiDownloader', 'logs')
    os.makedirs(app_data_dir, exist_ok=True)
        
    full_log_path = os.path.join(app_data_dir, log_file)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Mencegah log terganda jika dipanggil berkali-kali
    if not logger.handlers:
        file_handler = logging.FileHandler(full_log_path, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger