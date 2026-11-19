; 한 장 제주 오프라인 AI 팩 설치 프로그램 (Inno Setup 6, 명세 M01)
; 관리자 권한 없이 사용자 영역에 llama.cpp 서버와 모델을 설치한다. 한 장 제주 엔진이 이 위치를 찾아 쓴다
; (src/jeju_agent/aipack.py의 default_locations와 같은 경로).
; 빌드: python scripts/build_ai_pack.py windows-x64 --out output/ai-pack
;       iscc installer\HanJangJeju-AI.iss

#define AppName "한 장 제주 AI 팩"
#define AppVersion GetEnv("APP_VERSION")
#if AppVersion == ""
  #error "APP_VERSION must be read from pyproject.toml before building the installer"
#endif

[Setup]
AppId={{9C4D7E2A-5B1F-4A8E-B3C6-2E7F1A9D4B05}
; 한 장 제주가 켜져 있으면 닫아 달라고 안내한다. 엔진은 시작할 때만 팩을 찾으므로 다시 켜야 AI가 연결된다.
AppMutex=HanJangJeju.SingleInstance
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=한 장 제주
DefaultDirName={localappdata}\Programs\HanJangJeju-AI
DisableDirPage=yes
DisableProgramGroupPage=yes
CreateAppDir=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\output\installer
OutputBaseFilename=HanJangJeju-AI-Pack-{#AppVersion}
SetupIconFile=..\windows\HanJangJeju\app.ico
UninstallDisplayName={#AppName}
; 모델(GGUF)은 이미 압축된 것과 같아 다시 압축해도 거의 줄지 않는다. 시간만 들므로 빠른 압축을 쓴다.
Compression=lzma2/fast
SolidCompression=no
DiskSpanning=no
WizardStyle=modern

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Messages]
korean.FinishedLabel=AI 팩을 설치했어요. 한 장 제주를 다시 켜면 점검 화면에 "로컬 AI 준비됨"이 보여요. 처음 켤 때 모델을 불러오느라 1분쯤 걸릴 수 있어요.

[InstallDelete]
; 이전 팩의 서버 DLL과 모델을 먼저 지운다. llama.cpp는 서버 옆의 ggml-*.dll을 모두 읽어 들이므로
; 다른 빌드의 DLL이 남으면 서버가 멈출 수 있고, 이름이 바뀐 모델은 1GB가 그대로 남는다.
Type: filesandordirs; Name: "{app}\llama"
Type: filesandordirs; Name: "{app}\models"
Type: filesandordirs; Name: "{app}\licenses"

[Files]
Source: "..\output\ai-pack\ai-pack.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\output\ai-pack\README.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\output\ai-pack\llama\*"; DestDir: "{app}\llama"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\output\ai-pack\licenses\*"; DestDir: "{app}\licenses"; Flags: ignoreversion
Source: "..\output\ai-pack\models\*"; DestDir: "{app}\models"; Flags: ignoreversion nocompression

[UninstallDelete]
; 엔진이 남긴 것은 없다(서버 기록은 한 장 제주 자료 폴더에 쓴다). 설치한 폴더만 지운다.
Type: dirifempty; Name: "{app}"
