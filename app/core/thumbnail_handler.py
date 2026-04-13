import os
import subprocess
from app.utils.log_utils import setup_logger

logger = setup_logger("thumbnail_handler", "thumbnail_handler.log")

class ThumbnailHandler:
    @staticmethod
    def convert_thumbnail(input_file: str, output_format: str) -> str:
        """Mengonversi thumbnail ke format yang dipilih."""
        output_file = f"{os.path.splitext(input_file)[0]}.{output_format}"
        command = [
            "ffmpeg",
            "-i", input_file,
            output_file
        ]
        try:
            logger.info(f"Mengonversi {input_file} ke format {output_format}")
            subprocess.run(command, check=True)
            logger.info(f"Thumbnail berhasil dikonversi ke {output_file}")
            return output_file
        except subprocess.CalledProcessError as e:
            logger.error(f"Error saat konversi thumbnail: {e}")
            return ""
