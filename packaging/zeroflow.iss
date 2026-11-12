; Zero- Flow installer (Inno Setup 6.5 or later). Made by tools\build_installer.py, which
; passes /DAppVersion=<zeroflow.__version__> /DEdition=gpu|cpu /DSourceDir=<program folder>.
;
; - Per user: no admin prompt; installs to %LOCALAPPDATA%\Programs\ZeroFlow, like the
;   settings (%APPDATA%\ZeroFlow) and the Start-with-Windows key (HKCU).
; - One AppId for both editions: installing the other one replaces the first.
; - AppMutex: setup and the uninstaller wait while the Engine runs (its own lock).
; - The uninstaller asks before deleting data, "No" being the default (zeroflow/uninstall.py).
; Saved as UTF-8 with a BOM, for the Arabic text.

#ifndef AppVersion
  #error Build with tools\build_installer.py: it passes the version.
#endif
#ifndef Edition
  #error Build with tools\build_installer.py: it passes the edition.
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\" + Edition + "\ZeroFlow"
#endif
#if Edition == "gpu"
  #define EditionName "NVIDIA"
#else
  #define EditionName "CPU-light"
#endif

[Setup]
AppId={{475ECCFF-B278-43A4-8207-99892D7A9965}
AppName=Zero- Flow
AppVersion={#AppVersion}
AppVerName=Zero- Flow {#AppVersion} ({#EditionName})
AppPublisher=Zero- Flow
AppPublisherURL=https://github.com/zerocold7/zero-flow-app
DefaultDirName={autopf}\ZeroFlow
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
AppMutex=ZeroFlow.instance.dictation,ZeroFlow.instance.reader
OutputBaseFilename=ZeroFlow-{#AppVersion}-{#Edition}-setup
SetupIconFile=..\logo_tray.ico
UninstallDisplayIcon={app}\ZeroFlow.exe
UninstallDisplayName=Zero- Flow ({#EditionName})
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
LZMAUseSeparateProcess=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "arabic"; MessagesFile: "compiler:Languages\Arabic.isl"

[CustomMessages]
english.DeleteData=Also delete your settings, vocabulary, history, logs and downloaded models?%n%nYour API keys in Windows Credential Manager are deleted too. A models folder you chose yourself, outside Zero- Flow's own folders, is kept.%n%nNo keeps them, so a new install starts where you left off.
arabic.DeleteData=هل تريد أيضًا حذف إعداداتك والمفردات والسجل وملفات السجلات والنماذج المنزّلة؟%n%nتُحذف كذلك مفاتيح API المحفوظة في مدير بيانات الاعتماد في ويندوز. أما مجلد النماذج الذي اخترته بنفسك خارج مجلدات زيرو فلو فيبقى كما هو.%n%nاختيار «لا» يبقيها، فيبدأ التثبيت الجديد من حيث توقفت.
english.DataNotAllRemoved=Some of Zero- Flow's files could not be removed. You can delete these folders yourself:%n%n%1%n%2
arabic.DataNotAllRemoved=تعذر حذف بعض ملفات زيرو فلو. يمكنك حذف هذين المجلدين بنفسك:%n%n%1%n%2

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; The other edition's files (CUDA libraries in the GPU one) must not stay behind.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Excludes: "LICENSE.txt,THIRD-PARTY-NOTICES.txt"; Flags: ignoreversion recursesubdirs createallsubdirs
; GPL-3 (ADR 0003): the licence and the notices, with the source offer, ship with the program.
Source: "{#SourceDir}\LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDir}\THIRD-PARTY-NOTICES.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Zero- Flow"; Filename: "{app}\ZeroFlow.exe"
Name: "{autodesktop}\Zero- Flow"; Filename: "{app}\ZeroFlow.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ZeroFlow.exe"; Description: "{cm:LaunchProgram,Zero- Flow}"; Flags: nowait postinstall skipifsilent

[Code]
// Before the files go: ZeroFlow.exe --remove-startup always (a Run key pointing at a
// deleted program fails at every sign-in), or --remove-data when the user says Yes.
// A silent uninstall never deletes data.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Flag: String;
  ResultCode: Integer;
begin
  if CurUninstallStep <> usUninstall then
    Exit;
  Flag := '--remove-startup';
  if (not UninstallSilent) and
     (MsgBox(CustomMessage('DeleteData'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES) then
    Flag := '--remove-data';
  if not Exec(ExpandConstant('{app}\ZeroFlow.exe'), Flag, '', SW_HIDE,
              ewWaitUntilTerminated, ResultCode) then
    ResultCode := 1;
  if (Flag = '--remove-data') and (ResultCode <> 0) and (not UninstallSilent) then
    // (No line may start with "[": Inno Setup reads it as a section, even in [Code].)
    MsgBox(FmtMessage(CustomMessage('DataNotAllRemoved'), [
                      ExpandConstant('{userappdata}\ZeroFlow'),
                      ExpandConstant('{localappdata}\ZeroFlow')]), mbInformation, MB_OK);
end;
