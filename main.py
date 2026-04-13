import sys
import os
import traceback

# --- SISTEM PENGINTAI CRASH FATAL ---
# Menyimpan log crash di AppData agar terhindar dari Permission Error
log_dir = os.path.join(os.getenv('LOCALAPPDATA', 'C:\\'), 'KawaragiDownloader', 'logs')
os.makedirs(log_dir, exist_ok=True)
crash_log_path = os.path.join(log_dir, 'crash_report.txt')

def global_exception_handler(exc_type, exc_value, exc_traceback):
    """Menangkap SEMUA error yang menyebabkan Force Close"""
    with open(crash_log_path, 'w', encoding='utf-8') as f:
        f.write("=== FATAL CRASH REPORT (TERTANGKAP!) ===\n")
        traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)
    sys.__excepthook__(exc_type, exc_value, exc_traceback)

# Pasang pengintai ke sistem Windows
sys.excepthook = global_exception_handler

try:
    # Tambahkan root folder proyek ke sys.path
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

    from app.gui.main_window import MainWindow
    from PyQt5.QtWidgets import QApplication

    if __name__ == "__main__":
        app = QApplication(sys.argv)
        main_window = MainWindow()
        main_window.show()
        sys.exit(app.exec_())

except Exception as e:
    # Tangkap error jika terjadi saat mengimpor modul (sebelum GUI muncul)
    with open(crash_log_path, 'w', encoding='utf-8') as f:
        f.write("=== STARTUP CRASH (GAGAL LOADING) ===\n")
        traceback.print_exc(file=f)