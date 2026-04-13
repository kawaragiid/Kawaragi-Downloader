import logging
import os

def setup_logger(name: str, log_file: str, level=logging.INFO):
    """Membuat logger yang aman dari UAC Windows dengan menyimpannya di AppData."""
    
    # Dapatkan folder AppData milik user yang sedang aktif
    app_data_dir = os.path.join(os.getenv('LOCALAPPDATA'), 'KawaragiDownloader', 'logs')
    
    # Buat foldernya jika belum ada
    if not os.path.exists(app_data_dir):
        os.makedirs(app_data_dir)
        
    full_log_path = os.path.join(app_data_dir, log_file)

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Setup File Handler
    file_handler = logging.FileHandler(full_log_path, encoding='utf-8')
    file_handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Mencegah log terganda jika dipanggil berkali-kali
    if not logger.handlers:
        logger.addHandler(file_handler)

    return logger