; Inno Setup script for Husbandry Tracker (see docs/adr/0018-pyinstaller-innosetup-packaging.md).
;
; Expects packaging/husbandrytracker.spec to have already been built, with its output sitting at
; dist/HusbandryTracker/ (one folder up from this script) — see the GitHub Actions workflow
; (.github/workflows/release.yml) for the full build sequence.
;
; Build locally with (from the repo root, after `pyinstaller packaging/husbandrytracker.spec`):
;   iscc packaging\husbandrytracker.iss /DMyAppVersion=1.0.0
;
; MyAppVersion defaults to 0.0.0-dev for a manual build with no /D override; CI always passes the
; real version from the pushed git tag.

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0-dev"
#endif

#define MyAppName "Husbandry Tracker"
#define MyAppPublisher "CaskAbove"
#define MyAppURL "https://github.com/kevinramsey2002/HusbandryTracker"
#define MyAppExeName "HusbandryTrackerSupervisor.exe"
#define DistDir "..\dist\HusbandryTracker"

[Setup]
; Generated once for this project (reissued at the HerpMonitor -> Husbandry Tracker rename, ADR
; 0020, since no installer had shipped yet) — keep stable across releases so Windows treats every
; version as the same app (upgrade in place, one Add/Remove Programs entry) rather than a fresh
; install.
AppId={{36462FD1-575B-447F-BE5E-9061D7995BA3}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}/releases
; Per-user install, no admin rights / no UAC prompt (ADR 0018) — matches how the app already
; resolves data/db/logs relative to its own install folder.
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=HusbandryTrackerSetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Uninstalling removes only what this installer put down. data/ (database, logs, Reading/Care
; Event history) is created at runtime after install, is never listed in [Files] below, and so is
; never touched by the uninstaller — see ADR 0018's "leave data/ behind by default" decision.
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
