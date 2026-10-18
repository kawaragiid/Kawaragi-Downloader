import os
import json
import time

class Config:
    @staticmethod
    def get_app_data_dir() -> str:
        """Mendapatkan jalur aman untuk direktori data aplikasi di AppData."""
        local_appdata = os.getenv('LOCALAPPDATA')
        if not local_appdata:
            local_appdata = os.path.join(os.path.expanduser('~'), 'AppData', 'Local')
        app_data_dir = os.path.join(local_appdata, 'KawaragiDownloader')
        os.makedirs(app_data_dir, exist_ok=True)
        return app_data_dir

    @staticmethod
    def get_config_path() -> str:
        """Mendapatkan jalur file config di AppData."""
        return os.path.join(Config.get_app_data_dir(), 'config.json')

    @staticmethod
    def get_history_path() -> str:
        """Mendapatkan jalur file riwayat unduhan."""
        return os.path.join(Config.get_app_data_dir(), 'history.json')

    @staticmethod
    def load_config() -> dict:
        config_path = Config.get_config_path()
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    @staticmethod
    def save_config(data: dict):
        config_path = Config.get_config_path()
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Gagal menyimpan config: {e}")

    @staticmethod
    def save_last_directory(directory: str):
        data = Config.load_config()
        data['last_dir'] = directory
        Config.save_config(data)

    @staticmethod
    def load_last_directory() -> str:
        data = Config.load_config()
        last_dir = data.get('last_dir', '')
        if last_dir and os.path.exists(last_dir):
            return last_dir
        # Default ke folder Downloads pengguna jika belum diset
        downloads_dir = os.path.join(os.path.expanduser('~'), 'Downloads')
        if os.path.exists(downloads_dir):
            return downloads_dir
        return os.getcwd()

    @staticmethod
    def save_history_entry(entry: dict):
        """Menyimpan satu entri ke riwayat unduhan (maks 100 entri terbaru)."""
        history_path = Config.get_history_path()
        history = Config.load_history()
        
        entry['timestamp'] = entry.get('timestamp', time.strftime("%Y-%m-%d %H:%M:%S"))
        # Simpan di paling atas (terbaru)
        history.insert(0, entry)
        # Batasi ke 100 entri
        history = history[:100]
        
        try:
            with open(history_path, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Gagal menyimpan history: {e}")

    @staticmethod
    def load_history() -> list:
        history_path = Config.get_history_path()
        if os.path.exists(history_path):
            try:
                with open(history_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
            except Exception:
                pass
        return []

    @staticmethod
    def clear_history():
        history_path = Config.get_history_path()
        if os.path.exists(history_path):
            try:
                os.remove(history_path)
            except Exception:
                pass