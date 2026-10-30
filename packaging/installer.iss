; Inno Setup script for the Windows x64 installer.  iscc /DAppVersion=0.1.0 packaging\installer.iss
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6B0F3E0A-8C1D-4E7B-9A5C-2F3D7E1B4C90}
AppName=OVITO-Tachyon
AppVersion={#AppVersion}
AppPublisher=erwanjun
DefaultDirName={autopf}\OVITO-Tachyon
DefaultGroupName=OVITO-Tachyon
OutputDir=..\release
OutputBaseFilename=OVITO-Tachyon-{#AppVersion}-Windows-x64-setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\OVITO-Tachyon.exe
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2/max
SolidCompression=yes
PrivilegesRequiredOverridesAllowed=dialog
LicenseFile=..\LICENSE

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\OVITO-Tachyon\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\OVITO-Tachyon"; Filename: "{app}\OVITO-Tachyon.exe"
Name: "{autodesktop}\OVITO-Tachyon"; Filename: "{app}\OVITO-Tachyon.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\OVITO-Tachyon.exe"; Description: "{cm:LaunchProgram,OVITO-Tachyon}"; Flags: nowait postinstall skipifsilent
