[Setup]
AppName=Kawaragi Downloader
AppVersion=1.0
DefaultDirName={pf}\Kawaragi Downloader
DefaultGroupName=Kawaragi Downloader

[Files]
Source: "dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs
Source: "ffmpeg\*"; DestDir: "{app}\ffmpeg"; Flags: ignoreversion
