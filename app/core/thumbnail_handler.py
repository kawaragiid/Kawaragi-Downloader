import os
import subprocess
from app.utils.file_utils import get_ffmpeg_path
from app.utils.log_utils import setup_logger

logger = setup_logger("thumbnail_handler", "thumbnail_handler.log")

class ThumbnailHandler:
    @staticmethod
    def convert_thumbnail(input_file: str, output_format: str) -> str:
        """Mengonversi thumbnail ke format yang dipilih (jpg, png, webp)."""
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
            if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                logger.info(f"Thumbnail berhasil dikonversi ke {output_file}")
                # Hapus file mentah
                if input_file != output_file:
                    try:
                        os.remove(input_file)
                    except Exception:
                        pass
                return output_file
        except subprocess.CalledProcessError as e:
            logger.error(f"Error saat konversi thumbnail: {e}")
        return input_file
