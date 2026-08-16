#define MyAppName "N0TE"
#ifndef SourceDir
#define SourceDir "staging"
#endif
[Setup]
AppId={{7C56D54D-E2FA-46DD-A285-34656CA3767A}
AppName={#MyAppName}
AppVersion=1.2.4
DefaultDirName={autopf}\N0TE
DefaultGroupName=N0TE
OutputBaseFilename=N0TE-Windows-Setup
ArchitecturesAllowed=x64compatible arm64
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\N0TE.exe
Compression=lzma2
SolidCompression=yes
[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
[Icons]
Name: "{autoprograms}\N0TE"; Filename: "{app}\N0TE.exe"
[Run]
Filename: "{app}\N0TE.exe"; Description: "Launch N0TE"; Flags: nowait postinstall skipifsilent
