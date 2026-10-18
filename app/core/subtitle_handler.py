import os
import subprocess
from app.utils.file_utils import get_ffmpeg_path
from app.utils.log_utils import setup_logger

logger = setup_logger("subtitle_handler", "subtitle_handler.log")

class SubtitleHandler:
    @staticmethod
    def convert_subtitle(input_file: str, output_format: str) -> str:
        """Mengonversi subtitle ke format yang dipilih (srt, vtt, ass)."""
        if not os.path.exists(input_file):
            return ""
            
        base = os.path.splitext(input_file)[0]
        output_file = f"{base}.{output_format}"
        if input_file.lower() == output_file.lower():
            return input_file

        ffmpeg = get_ffmpeg_path()
        command = [ffmpeg, "-y", "-i", input_file, output_file]
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        try:
            logger.info(f"Mengonversi {input_file} ke format {output_format}")
            subprocess.run(command, check=True, creationflags=flags)
            if os.path.exists(output_file):
                logger.info(f"Subtitle berhasil dikonversi ke {output_file}")
                return output_file
        except subprocess.CalledProcessError as e:
            logger.error(f"Error saat konversi subtitle: {e}")
        return input_file
