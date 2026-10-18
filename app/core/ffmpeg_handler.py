import subprocess
import os
import shutil
import random
from app.utils.file_utils import get_ffmpeg_path
from app.utils.log_utils import setup_logger

logger = setup_logger("ffmpeg_handler", "ffmpeg.log")

class FFmpegHandler:
    def __init__(self, ffmpeg_path=None):
        self.ffmpeg_path = ffmpeg_path or get_ffmpeg_path()

    def convert(self, input_file: str, output_ext: str) -> str:
        """Konversi file ke format tujuan (mp4, webm, mp3, aac)."""
        if not os.path.exists(input_file):
            raise FileNotFoundError(f"File tidak ditemukan: {input_file}")

        base_path = os.path.splitext(input_file)[0]
        output_file = f"{base_path}.{output_ext}"
        
        if input_file.lower() == output_file.lower():
            return input_file

        command = [self.ffmpeg_path, "-y", "-i", input_file]
        
        if output_ext.lower() in ["mp3", "aac"]:
            if output_ext.lower() == "mp3":
                command += ["-vn", "-acodec", "libmp3lame", "-q:a", "2"]
            else:
                command += ["-vn", "-acodec", "aac", "-b:a", "192k"]
        elif output_ext.lower() == "mp4":
            command += ["-c:v", "libx264", "-preset", "fast", "-crf", "22", "-c:a", "aac", "-b:a", "192k"]
        elif output_ext.lower() == "webm":
            command += ["-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "0", "-c:a", "libopus"]
        else:
            command += ["-c", "copy"]
        
        command.append(output_file)
        logger.info(f"Menjalankan konversi FFmpeg: {' '.join(command)}")
        
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        subprocess.run(command, check=True, creationflags=flags)
        
        # Hapus file mentah setelah konversi berhasil
        if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
            if os.path.exists(input_file) and input_file != output_file:
                try:
                    os.remove(input_file)
                except Exception as e:
                    logger.warning(f"Gagal menghapus file mentah: {e}")
            return output_file
        return input_file

    def take_random_screenshots(self, input_file: str, count: int, duration: float, output_dir: str) -> list:
        """Mengambil screenshot secara acak di sepanjang durasi video."""
        if not os.path.exists(input_file) or duration <= 0 or count <= 0:
            return []

        shot_dir = os.path.join(output_dir, "kawaragi_temp_screenshots")
        if os.path.exists(shot_dir):
            try:
                shutil.rmtree(shot_dir)
            except Exception:
                pass
        os.makedirs(shot_dir, exist_ok=True)

        generated_files = []
        safe_duration = max(1.0, duration - 10.0)
        start_offset = min(5.0, duration * 0.1)
        
        timestamps = []
        for _ in range(count):
            time_ss = start_offset + (random.random() * safe_duration)
            timestamps.append(time_ss)
        
        timestamps.sort()

        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        for i, ts in enumerate(timestamps):
            outfile = os.path.join(shot_dir, f"shot_{i+1:03d}.jpg")
            command = [
                self.ffmpeg_path, "-y",
                "-ss", f"{ts:.2f}",
                "-i", input_file,
                "-vf", "scale=1280:-1",
                "-frames:v", "1",
                "-q:v", "2",
                outfile
            ]
            try:
                subprocess.run(command, check=True, creationflags=flags)
                if os.path.exists(outfile) and os.path.getsize(outfile) > 0:
                    generated_files.append(outfile)
            except Exception as e:
                logger.error(f"Gagal mengambil screenshot pada {ts:.2f}s: {e}")
                
        return generated_files