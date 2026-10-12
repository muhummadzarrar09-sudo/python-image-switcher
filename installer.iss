; UNSIGNED ALPHA — not yet verified on a clean Windows 11 machine.
; Build first: python build_editor.py
; Then compile with Inno Setup 6: iscc installer.iss
#define MyAppName "Image Switcher"
#define MyAppVersion "0.2.0-alpha.6"
#define MyAppPublisher "Image Switcher Team"
#define MyAppURL "https://github.com/muhummadzarrar09-sudo/python-image-switcher"
#define MyAppExeName "ImageSwitcherEditor.exe"

[Setup]
; Stable AppId: Inno Setup updates the existing installation rather than creating a second app.
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
LicenseFile=LICENSE.txt
OutputDir=dist
OutputBaseFilename=ImageSwitcher-Setup-{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "dist\ImageSwitcherEditor\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
