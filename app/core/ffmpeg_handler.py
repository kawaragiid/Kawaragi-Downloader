import subprocess
import os
import shutil
import random

class FFmpegHandler:
    def __init__(self, ffmpeg_path="ffmpeg"):
        self.ffmpeg_path = ffmpeg_path

    def convert(self, input_file, output_ext):
        """Konversi file ke format tujuan (mp4, mp3, dll)."""
        base_path = os.path.splitext(input_file)[0]
        output_file = f"{base_path}.{output_ext}"
        
        if input_file.lower() == output_file.lower():
            return input_file

        command = [self.ffmpeg_path, "-y", "-i", input_file]
        if output_ext in ["mp3", "aac"]:
            command += ["-vn", "-acodec", "libmp3lame" if output_ext == "mp3" else "aac", "-q:a", "2"]
        elif output_ext == "mp4":
            command += ["-c:v", "libx264", "-preset", "fast", "-c:a", "aac"]
        
        command.append(output_file)
        subprocess.run(command, check=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        
        if os.path.exists(input_file) and input_file != output_file:
            os.remove(input_file)
        return output_file

    def take_random_screenshots(self, input_file, count, duration, output_dir):
        """Mengambil screenshot secara acak di sepanjang durasi video."""
        shot_dir = os.path.join(output_dir, "kawaragi_temp_screenshots")
        if os.path.exists(shot_dir): shutil.rmtree(shot_dir) # Bersihkan sampah lama
        os.makedirs(shot_dir)

        if duration <= 0: return []

        generated_files = []
        
        # Hitung titik-titik acak (hindari 5 detik awal/akhir)
        safe_duration = max(0, duration - 10)
        timestamps = []
        for _ in range(count):
            # Ambil detik acak
            time_ss = 5 + (random.random() * safe_duration)
            timestamps.append(time_ss)
        
        # Urutkan agar FFmpeg bekerja lebih efisien
        timestamps.sort()

        for i, ts in enumerate(timestamps):
            outfile = os.path.join(shot_dir, f"shot_{i:03d}.jpg")
            
            # Perintah FFmpeg cepat dengan Seeking (-ss sebelum -i)
            command = [
                self.ffmpeg_path, "-y",
                "-ss", str(ts), # Lompat ke waktu acak
                "-i", input_file,
                "-vf", "scale=1280:-1", # Resizing ke 720p
                "-frames:v", "1", # Ambil 1 frame
                "-q:v", "2", # Kualitas tinggi
                outfile
            ]
            subprocess.run(command, check=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            if os.path.exists(outfile):
                generated_files.append(outfile)
                
        return generated_files