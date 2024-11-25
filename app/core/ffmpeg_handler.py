import subprocess
import os

class FFmpegHandler:
    def __init__(self, ffmpeg_path="ffmpeg/ffmpeg.exe"):
        self.ffmpeg_path = ffmpeg_path

    def convert_to_mp3(self, input_file, output_file):
        command = [
            self.ffmpeg_path,
            '-i', input_file,
            '-q:a', '0',
            '-map', 'a',
            output_file
        ]
        subprocess.run(command)
