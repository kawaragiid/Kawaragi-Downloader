[Setup]
AppName=Kawaragi Downloader
AppVersion=26.0
DefaultDirName={autopf}\Kawaragi Downloader
DefaultGroupName=Kawaragi Downloader
OutputDir=Output
OutputBaseFilename=Kawaragi_Setup_v1.0
; Menggunakan logo Anda sebagai ikon file Setup-nya
SetupIconFile=assets\logo.ico 
Compression=lzma
SolidCompression=yes

[Files]
; 1. Mengambil semua isi folder hasil build PyInstaller
Source: "dist\KawaragiDownloader\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs

; 2. Mengambil FFmpeg (Pastikan ffmpeg.exe ada di folder root proyek Anda)
Source: "ffmpeg.exe"; DestDir: "{app}"; Flags: ignoreversion

; 3. Mengambil folder Ekstensi Chrome
Source: "Kawaragi-Trigger\*"; DestDir: "{app}\Kawaragi-Trigger"; Flags: ignoreversion recursesubdirs

[Tasks]
Name: "desktopicon"; Description: "Buat shortcut di Desktop"; GroupDescription: "Ikon Tambahan:"

[Icons]
; Membuat shortcut di Start Menu
Name: "{group}\Kawaragi Downloader"; Filename: "{app}\KawaragiDownloader.exe"
; Membuat shortcut di Desktop
Name: "{autodesktop}\Kawaragi Downloader"; Filename: "{app}\KawaragiDownloader.exe"; Tasks: desktopicon