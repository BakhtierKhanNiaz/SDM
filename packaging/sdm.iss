; Inno Setup script for SDM's per-user installer (M10, ADR-0018).
; Built by: uv run python scripts/build_release.py --installer
;
; - Per user, no administrator rights: installs to %LOCALAPPDATA%\Programs\SDM.
; - A Start-menu shortcut (a desktop one if chosen).
; - Uninstalling removes the program and SDM's Chrome registration (the per-user registry key
;   and the two host files), but keeps the history, settings, logs and every downloaded file
;   (%LOCALAPPDATA%\SDM and the download folders).

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\SDM"
#endif

[Setup]
; The AppId never changes: it lets a new version upgrade an installed one.
AppId={{4019A688-E755-4AC6-A58B-D453C61ACC6F}
AppName=SDM
AppVersion={#AppVersion}
AppVerName=SDM {#AppVersion}
AppPublisher=SDM (personal use)
DefaultDirName={autopf}\SDM
DefaultGroupName=SDM
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputBaseFilename=SDM-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\SDM.exe
UninstallDisplayName=SDM (Smart Download Manager)
; Close a running SDM before replacing or removing its files.
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\SDM"; Filename: "{app}\SDM.exe"; Comment: "Smart Download Manager"
Name: "{autodesktop}\SDM"; Filename: "{app}\SDM.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\SDM.exe"; Description: "Start SDM now"; Flags: nowait postinstall skipifsilent

[Registry]
; Created by SDM (Help > Set up Chrome integration), never by the installer ("dontcreatekey");
; removed on uninstall so Chrome isn't left pointing at a deleted program.
Root: HKCU; Subkey: "Software\Google\Chrome\NativeMessagingHosts\com.sdm.bridge"; Flags: uninsdeletekey dontcreatekey

[UninstallDelete]
Type: files; Name: "{localappdata}\SDM\bridge\com.sdm.bridge.json"
Type: files; Name: "{localappdata}\SDM\bridge\sdm-bridge-host.bat"
Type: dirifempty; Name: "{localappdata}\SDM\bridge"
