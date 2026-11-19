; 한 장 제주 설치 프로그램 (Inno Setup 6)
; 관리자 권한 없이 사용자 영역에 설치한다. 센터 PC의 공용 계정에서도 설치할 수 있게 하기 위해서다.
; 빌드: iscc installer\HanJangJeju.iss  (output\app 에 WPF 프로그램과 engine 폴더가 있어야 한다)
; AI 포함판(B01): iscc /DWithAI installer\HanJangJeju.iss  (output\ai-pack 도 있어야 한다)
;   미포함판과 같은 AppId라 서로 덮어 설치하고 같은 제거 프로그램을 쓴다. AI 팩은 {app}\ai-pack에 들어가
;   앱을 지우면 함께 지워진다. 포함판 위에 미포함판을 설치해도 ai-pack은 지우지 않는다(AI가 갑자기 사라지지 않게).

#define AppName "한 장 제주"
#define AppVersion GetEnv("APP_VERSION")
#if AppVersion == ""
  #error "APP_VERSION must be read from pyproject.toml before building the installer"
#endif
#ifdef WithAI
  #define Edition "-AI"
#else
  #define Edition ""
#endif

[Setup]
AppId={{6B1E2C7A-3F2D-4C1B-9E5A-0D6F8A2B7C11}
; 프로그램(App.xaml.cs)이 같은 이름의 mutex를 쥔다. 설치/제거 때 실행 중이면 닫아 달라고 안내한다(P03).
AppMutex=HanJangJeju.SingleInstance
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppName}
DefaultDirName={localappdata}\Programs\HanJangJeju
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; 누를 일을 줄인다(토스: 한 화면에 한 가지). 설치 위치는 관리자 권한 없이 쓸 수 있는 사용자 영역으로 고정하고,
; '준비 완료' 확인 화면은 건너뛴다. 남는 화면: 바로가기 선택 → 설치 중 → 완료.
DisableDirPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\output\installer
OutputBaseFilename=HanJangJeju-Setup{#Edition}-{#AppVersion}
SetupIconFile=..\windows\HanJangJeju\app.ico
UninstallDisplayIcon={app}\HanJangJeju.exe
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
; 설치 마법사 그림: 왼쪽 큰 그림(비율 164:314)과 오른쪽 위 작은 그림(정사각). 화면 배율에 가장 맞는 크기를 Setup이 고른다.
; 모든 Inno Setup 6 버전에서 읽히도록 24비트 BMP를 쓴다. 원본 로고: assets/brand/logo-v2.png
WizardImageFile=wizard\large-164x314.bmp,wizard\large-202x386.bmp,wizard\large-336x643.bmp,wizard\large-430x824.bmp
WizardSmallImageFile=wizard\small-58.bmp,wizard\small-97.bmp,wizard\small-124.bmp

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Messages]
; Inno Setup 기본 한국어 문구("마법사", "하시겠습니까")를 앱과 같은 해요체로 바꾼다. 이름은 조사를 맞추려고 직접 쓴다.
korean.SetupWindowTitle=%1 설치
korean.WizardSelectTasks=바로가기를 만들까요?
korean.SelectTasksDesc=바탕화면에서 한 번에 열 수 있게 해 드려요.
korean.SelectTasksLabel2=필요 없으면 체크를 풀고 [설치]를 눌러 주세요.
korean.WizardInstalling=설치하고 있어요
korean.InstallingLabel=한 장 제주를 이 PC에 설치하고 있어요. 잠시만 기다려 주세요.
korean.FinishedHeadingLabel=한 장 제주를 쓸 준비가 됐어요
korean.FinishedLabelNoIcons=인터넷 없이 이 PC 안에서만 동작해요.
korean.FinishedLabel=시작 메뉴나 바탕화면의 '한 장 제주'로 언제든 다시 열 수 있어요. 인터넷 없이 이 PC 안에서만 동작해요.
korean.ClickFinish=[마침]을 누르면 이 창이 닫혀요.
korean.ExitSetupMessage=설치가 아직 끝나지 않았어요. 지금 그만두면 한 장 제주가 설치되지 않아요.%n%n그래도 그만둘까요?

[Tasks]
Name: "desktopicon"; Description: "바탕화면에 바로가기 만들기"; GroupDescription: "바로가기:"

#ifdef WithAI
[InstallDelete]
; 이전 팩의 DLL과 모델이 남으면 llama.cpp가 다른 빌드의 ggml-*.dll을 읽어 멈출 수 있다(M05와 같은 이유)
Type: filesandordirs; Name: "{app}\ai-pack"
#endif

[Files]
Source: "..\output\app\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
#ifdef WithAI
Source: "..\output\ai-pack\ai-pack.json"; DestDir: "{app}\ai-pack"; Flags: ignoreversion
Source: "..\output\ai-pack\README.txt"; DestDir: "{app}\ai-pack"; Flags: ignoreversion
Source: "..\output\ai-pack\llama\*"; DestDir: "{app}\ai-pack\llama"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\output\ai-pack\licenses\*"; DestDir: "{app}\ai-pack\licenses"; Flags: ignoreversion
; 모델은 이미 압축된 것과 같아 다시 압축하지 않는다(ultra64 solid로 1GB를 압축하면 시간만 든다)
Source: "..\output\ai-pack\models\*"; DestDir: "{app}\ai-pack\models"; Flags: ignoreversion nocompression
#endif

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\HanJangJeju.exe"
Name: "{group}\{#AppName} (웹 브라우저로 열기)"; Filename: "{app}\engine\jeju-engine.exe"; Parameters: "--open"; WorkingDir: "{app}\engine"
Name: "{group}\{#AppName} 지우기"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\HanJangJeju.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\HanJangJeju.exe"; Description: "지금 한 장 제주 열기"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 프로그램을 지우면 이용자가 넣은 자료와 결과, 기록도 함께 지운다(센터 탑재 조건: 결과 삭제).
Type: filesandordirs; Name: "{localappdata}\HanJangJeju"
