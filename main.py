import sys
import os

def validate_environment():
    """Memastikan environment Python valid."""
    # Pastikan virtual environment aktif
    if not hasattr(sys, 'real_prefix') and not hasattr(sys, 'base_prefix'):
        print("Error: Virtual environment tidak aktif.")
        sys.exit(1)

    # Pastikan dependensi terinstal
    try:
        import PyQt5
        import yt_dlp
    except ImportError as e:
        print(f"Error: Dependensi tidak ditemukan: {e.name}")
        sys.exit(1)

# Validasi environment sebelum melanjutkan
validate_environment()

# Tambahkan root folder proyek ke `sys.path`
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.gui.main_window import MainWindow
from PyQt5.QtWidgets import QApplication

if __name__ == "__main__":
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    try:
        sys.exit(app.exec_())
    except KeyboardInterrupt:
        print("Aplikasi dihentikan oleh pengguna.")
