[Setup]
; AppId sangat penting agar Windows tahu ini aplikasi yang sama (bisa di-repair/uninstall)
AppId={{KAWARAGI-DOWNLOADER-V1-000000}
AppName=Kawaragi Downloader
AppVersion=26.0
DefaultDirName={autopf}\Kawaragi Downloader
DefaultGroupName=Kawaragi Downloader
OutputDir=Output
OutputBaseFilename=Kawaragi_Setup_v26.0
SetupIconFile=assets\logo.ico
Compression=lzma
SolidCompression=yes

; Memaksa aplikasi tertutup jika user mencoba install ulang saat app sedang jalan
CloseApplications=yes
RestartApplications=no

; Menampilkan logo Abang di menu Uninstall Windows
UninstallDisplayIcon={app}\KawaragiDownloader.exe

[InstallDelete]
; INI KUNCI AUTO-CLEAN: Menghapus jeroan lama sebelum menimpa dengan yang baru
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\Kawaragi-Trigger"
Type: files; Name: "{app}\ffmpeg.exe"

[Files]
Source: "dist\KawaragiDownloader\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs
Source: "ffmpeg.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "Kawaragi-Trigger\*"; DestDir: "{app}\Kawaragi-Trigger"; Flags: ignoreversion recursesubdirs

[Tasks]
Name: "desktopicon"; Description: "Buat shortcut di Desktop"; GroupDescription: "Ikon Tambahan:"

[Icons]
Name: "{group}\Kawaragi Downloader"; Filename: "{app}\KawaragiDownloader.exe"
Name: "{autodesktop}\Kawaragi Downloader"; Filename: "{app}\KawaragiDownloader.exe"; Tasks: desktopicon