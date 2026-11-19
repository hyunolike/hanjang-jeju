#!/usr/bin/env bash
# Mac 앱(.app)과 설치 이미지(.dmg)를 만든다.
# 사용(저장소 루트): mac/build-app.sh                       # 이 Mac의 칩(arm64 또는 x64)용 미포함판
#                    AI_PACK=output/ai-pack mac/build-app.sh  # 미포함판과 AI 포함판을 함께 만든다(B01)
# 결과: output/mac/HanJangJeju.app, output/mac/HanJangJeju-<project.version>-<arch>.dmg
#       (AI_PACK이 있으면) output/mac/ai/HanJangJeju.app, output/mac/HanJangJeju-AI-<project.version>-<arch>.dmg
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION=$(uv run python scripts/release_version.py)
[ "${APP_VERSION:-$VERSION}" = "$VERSION" ] || { echo "APP_VERSION과 pyproject.toml 버전이 달라요" >&2; exit 1; }
case "$(uname -m)" in arm64) ARCH=arm64 ;; *) ARCH=x64 ;; esac
if [ -n "${AI_PACK:-}" ]; then
  # 잘못된 경로를 미포함판을 다 만든 뒤에야 알지 않게 먼저 확인한다. 출력 폴더 안이면 아래 rm -rf로 지워진다.
  [ -f "$AI_PACK/ai-pack.json" ] || { echo "AI_PACK에 ai-pack.json이 없어요: $AI_PACK" >&2; exit 1; }
  case "$(cd "$AI_PACK" && pwd)" in "$(pwd)/output/mac"*) echo "AI_PACK은 output/mac 밖에 두어야 해요" >&2; exit 1 ;; esac
fi
OUT=output/mac
APP="$OUT/HanJangJeju.app"
rm -rf "$OUT" && mkdir -p "$OUT"

echo "1/5 화면 빌드"
[ -d web/dist ] || (cd web && pnpm install --frozen-lockfile && pnpm build)

echo "2/5 엔진 묶기"
uv run pyinstaller packaging/engine.spec --noconfirm --distpath output/dist --workpath output/build >/dev/null

echo "3/5 앱 창 빌드 (Photino.NET)"
dotnet publish mac/HanJangJeju.Mac -c Release -r "osx-$ARCH" --self-contained true -o "$OUT/publish" >/dev/null

echo "4/5 앱 묶음 만들기"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp -R "$OUT/publish/." "$APP/Contents/MacOS/"
cp -R output/dist/jeju-engine "$APP/Contents/Resources/engine"
ICONSET="$OUT/app.iconset"
mkdir -p "$ICONSET"
for s in 16 32 128 256 512; do
  sips -z $s $s windows/HanJangJeju/logo.png --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
  sips -z $((s*2)) $((s*2)) windows/HanJangJeju/logo.png --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/app.icns"
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>HanJangJeju</string>
  <key>CFBundleDisplayName</key><string>한 장 제주</string>
  <key>CFBundleIdentifier</key><string>kr.hanjangjeju.app</string>
  <key>CFBundleVersion</key><string>$VERSION</string>
  <key>CFBundleShortVersionString</key><string>$VERSION</string>
  <key>CFBundleExecutable</key><string>HanJangJeju</string>
  <key>CFBundleIconFile</key><string>app.icns</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSAppTransportSecurity</key><dict><key>NSAllowsLocalNetworking</key><true/></dict>
</dict></plist>
PLIST
# 개발자 인증서가 없으므로 임시 서명(ad-hoc)만 한다. 처음 열 때 macOS 15 이후는 '시스템 설정 > 그래도 열기'가 필요하다.
codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || true

make_dmg() { # $1 앱 묶음, $2 결과 dmg
  local stage="$OUT/dmg"
  rm -rf "$stage" && mkdir -p "$stage"
  cp -R "$1" "$stage/"
  ln -s /Applications "$stage/Applications"
  hdiutil create -volname "한 장 제주" -srcfolder "$stage" -ov -format UDZO "$2" >/dev/null
  rm -rf "$stage"
}

echo "5/5 설치 이미지(.dmg) 만들기"
make_dmg "$APP" "$OUT/HanJangJeju-$VERSION-$ARCH.dmg"

if [ -n "${AI_PACK:-}" ]; then
  echo "AI 포함판: 앱 안 Contents/Resources/ai-pack에 AI 팩을 넣는다(B02)"
  APP_AI="$OUT/ai/HanJangJeju.app"
  mkdir -p "$OUT/ai"
  ditto "$APP" "$APP_AI"
  ditto "$AI_PACK" "$APP_AI/Contents/Resources/ai-pack"
  # 복사한 앱에 1GB를 더해 기존 봉인이 깨졌으므로 다시 서명하고, 서명이 맞지 않으면 dmg를 만들지 않는다.
  # (깨진 서명의 앱은 Apple 칩에서 "손상됨"으로 열리지 않을 수 있고, CI의 엔진 직접 실행 검사로는 드러나지 않는다)
  codesign --force --deep --sign - "$APP_AI" >/dev/null
  codesign --verify --deep --strict "$APP_AI" || { echo "AI 포함판 서명이 맞지 않아요" >&2; exit 1; }
  make_dmg "$APP_AI" "$OUT/HanJangJeju-AI-$VERSION-$ARCH.dmg"
fi
rm -rf "$ICONSET" "$OUT/publish"
du -sh "$APP" "$OUT"/*.dmg
