; Inno Setup Script for Python Image Switcher
; Creates a real Windows Setup.exe installer
; Install Inno Setup from https://jrsoftware.org/isinfo.php
; Compile with: iscc installer.iss

#define MyAppName "Image Switcher"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Image Switcher Team"
#define MyAppURL "https://github.com/muhummadzarrar09-sudo/python-image-switcher"
#define MyAppExeName "ImageSwitcher.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DisableDirPage=no
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=LICENSE.txt
OutputDir=dist
OutputBaseFilename=ImageSwitcher-Setup-{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "associate"; Description: "Associate image files with Image Switcher (optional)"; GroupDescription: "File associations:"

[Files]
; OneFile build
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion; Tasks: ; Check: FileExists(ExpandConstant('dist\{#MyAppExeName}'))
; OneDir build fallback - include whole folder
Source: "dist\ImageSwitcher\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Check: DirExists(ExpandConstant('dist\ImageSwitcher'))

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\__pycache__"
Type: filesandordirs; Name: "{localappdata}\{#MyAppName}"

[Code]
function DirExists(const DirName: string): Boolean;
begin
  Result := DirExists(DirName);
end;

procedure InitializeWizard;
begin
  // Custom wizard init if needed
end;
