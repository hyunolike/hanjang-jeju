; 한 장 제주 설치 프로그램 (Inno Setup 6)
; 관리자 권한 없이 사용자 영역에 설치한다. 센터 PC의 공용 계정에서도 설치할 수 있게 하기 위해서다.
; 빌드: iscc installer\HanJangJeju.iss  (output\app 에 WPF 프로그램과 engine 폴더가 있어야 한다)

#define AppName "한 장 제주"
#define AppVersion GetEnv("APP_VERSION")
#if AppVersion == ""
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{6B1E2C7A-3F2D-4C1B-9E5A-0D6F8A2B7C11}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppName}
DefaultDirName={localappdata}\Programs\HanJangJeju
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\output\installer
OutputBaseFilename=HanJangJeju-Setup-{#AppVersion}
SetupIconFile=..\windows\HanJangJeju\app.ico
UninstallDisplayIcon={app}\HanJangJeju.exe
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕화면에 바로가기 만들기"; GroupDescription: "바로가기:"

[Files]
Source: "..\output\app\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\HanJangJeju.exe"
Name: "{group}\{#AppName} (웹 브라우저로 열기)"; Filename: "{app}\engine\jeju-engine.exe"; Parameters: "--open"; WorkingDir: "{app}\engine"
Name: "{group}\{#AppName} 지우기"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\HanJangJeju.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\HanJangJeju.exe"; Description: "지금 실행하기"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 프로그램을 지우면 이용자가 넣은 자료와 결과, 기록도 함께 지운다(센터 탑재 조건: 결과 삭제).
Type: filesandordirs; Name: "{localappdata}\HanJangJeju"
