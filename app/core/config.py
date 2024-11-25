import os
import json

CONFIG_FILE = "config.json"

class Config:
    @staticmethod
    def save_last_directory(directory: str):
        """Simpan direktori terakhir yang digunakan ke dalam file konfigurasi."""
        config = Config._load_config()
        config['last_directory'] = directory
        Config._save_config(config)

    @staticmethod
    def load_last_directory() -> str:
        """Muat direktori terakhir dari file konfigurasi."""
        config = Config._load_config()
        return config.get('last_directory', "")

    @staticmethod
    def _load_config() -> dict:
        if not os.path.exists(CONFIG_FILE):
            return {}
        with open(CONFIG_FILE, 'r') as file:
            return json.load(file)

    @staticmethod
    def _save_config(config: dict):
        with open(CONFIG_FILE, 'w') as file:
            json.dump(config, file, indent=4)
