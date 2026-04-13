import os
import json

class Config:
    @staticmethod
    def get_config_path():
        """Mendapatkan jalur aman untuk file config di AppData."""
        app_data_dir = os.path.join(os.getenv('LOCALAPPDATA'), 'KawaragiDownloader')
        if not os.path.exists(app_data_dir):
            os.makedirs(app_data_dir)
        return os.path.join(app_data_dir, 'config.json')

    @staticmethod
    def save_last_directory(directory: str):
        config_path = Config.get_config_path()
        data = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    data = json.load(f)
            except: pass
            
        data['last_dir'] = directory
        
        try:
            with open(config_path, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            print(f"Gagal menyimpan config: {e}")

    @staticmethod
    def load_last_directory() -> str:
        config_path = Config.get_config_path()
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    data = json.load(f)
                    return data.get('last_dir', '')
            except: pass
        return ""