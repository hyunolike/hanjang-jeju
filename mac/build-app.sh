#!/usr/bin/env bash
# Mac 앱(.app)과 설치 이미지(.dmg)를 만든다.
# 사용(저장소 루트): mac/build-app.sh            # 이 Mac의 칩(arm64 또는 x64)용
# 결과: output/mac/HanJangJeju.app, output/mac/HanJangJeju-1.0.0-<arch>.dmg
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION="${APP_VERSION:-1.0.0}"
case "$(uname -m)" in arm64) ARCH=arm64 ;; *) ARCH=x64 ;; esac
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
# 개발자 인증서가 없으므로 임시 서명(ad-hoc)만 한다. 처음 열 때 '우클릭 > 열기'가 필요하다.
codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || true

echo "5/5 설치 이미지(.dmg) 만들기"
STAGE="$OUT/dmg"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname "한 장 제주" -srcfolder "$STAGE" -ov -format UDZO "$OUT/HanJangJeju-$VERSION-$ARCH.dmg" >/dev/null
rm -rf "$STAGE" "$ICONSET" "$OUT/publish"
du -sh "$APP" "$OUT"/*.dmg
