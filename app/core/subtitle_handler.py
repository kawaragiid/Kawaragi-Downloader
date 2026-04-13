import os
import subprocess
from app.utils.log_utils import setup_logger

logger = setup_logger("subtitle_handler", "subtitle_handler.log")

class SubtitleHandler:
    @staticmethod
    def convert_subtitle(input_file: str, output_format: str) -> str:
        """Mengonversi subtitle ke format yang dipilih."""
        output_file = f"{os.path.splitext(input_file)[0]}.{output_format}"
        command = [
            "ffmpeg",
            "-i", input_file,
            output_file
        ]
        try:
            logger.info(f"Mengonversi {input_file} ke format {output_format}")
            subprocess.run(command, check=True)
            logger.info(f"Subtitle berhasil dikonversi ke {output_file}")
            return output_file
        except subprocess.CalledProcessError as e:
            logger.error(f"Error saat konversi subtitle: {e}")
            return ""
