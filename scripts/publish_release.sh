#!/usr/bin/env bash
# 세 설치판과 체크섬을 draft에 모두 올린 뒤 공개한다. published Release는 수정하지 않는다.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
DIST="${1:-dist}"
REPO="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY가 필요합니다}"
TAG="${GITHUB_REF_NAME:?GITHUB_REF_NAME이 필요합니다}"
VERSION=$(python3 "$ROOT/scripts/release_version.py" --check-tag "$TAG")
[ "${APP_VERSION:-$VERSION}" = "$VERSION" ] || { echo "APP_VERSION과 원본 버전이 달라요" >&2; exit 1; }

# gh release view는 GraphQL로 pending tag의 draft도 찾는다. REST /tags는 published만 찾는다.
state=$(gh release view "$TAG" --repo "$REPO" --json isDraft,databaseId 2>/dev/null) || state=""
if [ -n "$state" ]; then
  draft=$(python3 -c 'import json,sys; print(str(json.load(sys.stdin)["isDraft"]).lower())' <<< "$state")
  if [ "$draft" = false ]; then echo "release skip: $TAG is already published"; exit 0; fi
fi

FILES=(HanJangJeju-Setup-windows-x64.exe HanJangJeju-mac-arm64.dmg HanJangJeju-mac-x64.dmg SHA256SUMS.txt)
for file in "${FILES[@]}"; do
  [ -s "$DIST/$file" ] || { echo "설치판 파일이 없어요: $file" >&2; exit 1; }
done
python3 - "$DIST" "${FILES[@]:0:3}" <<'PY'
import hashlib
from pathlib import Path
import re
import sys
base = Path(sys.argv[1])
expected = set(sys.argv[2:])
lines = (base / "SHA256SUMS.txt").read_text().splitlines()
checksums = {}
for line in lines:
    match = re.fullmatch(r"([0-9a-f]{64}) [ *](.+)", line)
    if not match or match[2] in checksums:
        raise SystemExit("invalid checksum manifest")
    checksums[match[2]] = match[1]
if set(checksums) != expected:
    raise SystemExit("checksum manifest must cover exactly three installers")
for name, digest in checksums.items():
    with (base / name).open("rb") as file:
        if hashlib.file_digest(file, "sha256").hexdigest() != digest:
            raise SystemExit("installer checksum mismatch")
PY

if [ -z "$state" ]; then
  gh release create "$TAG" --repo "$REPO" --draft --verify-tag --title "한 장 제주 $TAG" --notes-file "$ROOT/RELEASE_NOTES.md"
  state=$(gh release view "$TAG" --repo "$REPO" --json isDraft,databaseId)
fi
id=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["databaseId"])' <<< "$state")
ASSETS=()
for file in "${FILES[@]}"; do ASSETS+=("$DIST/$file"); done
gh release upload "$TAG" --repo "$REPO" "${ASSETS[@]}" --clobber
# semantic version 기준으로 Latest를 선택해 늦게 끝난 이전 버전이 최신을 덮지 않게 한다.
gh api --method PATCH "repos/$REPO/releases/$id" -F draft=false -f make_latest=legacy >/dev/null
echo "release published: $TAG"
