"""오프라인 AI 팩 폴더를 만든다 (명세 M05). 표준 라이브러리만 쓴다.

사용(저장소 루트): python3 scripts/build_ai_pack.py windows-x64 --crt-dir <VC 재배포 x64 폴더> [--out output/ai-pack] [--cache output/ai-pack-cache]
                  python3 scripts/build_ai_pack.py macos-arm64 [--out ...]
결과: <out>/ai-pack.json, llama/, models/, licenses/, README.txt

packaging/ai-pack/sources.json에 고정한 URL만 내려받고 SHA256이 하나라도 다르면 아무것도 만들지 않는다.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import shutil
import struct
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "packaging/ai-pack/sources.json"

# llama.cpp Windows 묶음은 MSVC 런타임을 따로 싣지 않는다. VC++ 재배포 패키지가 없는 새 PC에서도 켜지도록
# Microsoft가 앱 폴더 배포를 허용하는 x64 CRT DLL을 서버 옆에 넣는다(M6).
CRT_DLLS = ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll")
# Windows 10/11에 항상 있는 시스템 DLL. api-ms-win-*는 Windows 10부터 내장된 Universal CRT다.
SYSTEM_DLLS = {"kernel32.dll", "advapi32.dll", "ws2_32.dll", "crypt32.dll", "psapi.dll", "user32.dll", "shell32.dll",
               "ole32.dll", "oleaut32.dll", "bcrypt.dll", "ntdll.dll", "shlwapi.dll", "dbghelp.dll", "iphlpapi.dll"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(url: str, expected: str, cache: Path) -> Path:
    """캐시에 같은 해시의 파일이 있으면 그대로 쓰고, 없으면 받은 뒤 해시를 확인한다."""
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / f"{expected[:16]}-{url.rsplit('/', 1)[-1]}"
    if target.exists() and sha256(target) == expected:
        return target
    partial = target.with_suffix(target.suffix + ".part")
    for attempt in range(1, 4):
        print(f"받는 중({attempt}/3): {url}", flush=True)
        try:
            with urllib.request.urlopen(url, timeout=60) as res, partial.open("wb") as out:
                shutil.copyfileobj(res, out, 1 << 20)
            break
        except (urllib.error.URLError, TimeoutError, ConnectionError) as err:
            if attempt == 3:
                raise SystemExit(f"내려받지 못했어요: {url} ({err})") from err
            time.sleep(5 * attempt)
    actual = sha256(partial)
    if actual != expected:
        partial.unlink()
        raise SystemExit(f"SHA256이 달라요: {url}\n  기대 {expected}\n  실제 {actual}")
    partial.replace(target)
    return target


def _safe_members(names: list[str]) -> None:
    for name in names:
        if name.startswith(("/", "\\")) or ".." in Path(name).parts:
            raise SystemExit(f"압축 파일 안에 위험한 경로가 있어요: {name}")


def extract_server(archive: Path, keep: list[str], dest: Path) -> list[str]:
    """llama.cpp 압축에서 서버 실행에 필요한 파일만 꺼낸다. 폴더 구조는 버리고 한 폴더에 둔다."""
    dest.mkdir(parents=True, exist_ok=True)
    kept = []
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        if archive.name.endswith(".zip"):
            with zipfile.ZipFile(archive) as z:
                _safe_members(z.namelist())
                z.extractall(tmpdir)
        else:
            with tarfile.open(archive) as t:
                _safe_members(t.getnames())
                if hasattr(tarfile, "data_filter"):  # Python 3.11.4+
                    t.extractall(tmpdir, filter="data")
                else:
                    t.extractall(tmpdir)
        for path in sorted(tmpdir.rglob("*")):
            if path.is_file() and not path.is_symlink() and any(fnmatch.fnmatch(path.name, p) for p in keep):
                shutil.copy2(path, dest / path.name)
                kept.append(path.name)
        # macOS 묶음은 libfoo.dylib → libfoo.0.dylib 같은 심볼릭 링크로 찾는다. 링크 대신 실제 파일을 복사한다.
        for path in sorted(tmpdir.rglob("*")):
            if path.is_symlink() and any(fnmatch.fnmatch(path.name, p) for p in keep) and not (dest / path.name).exists():
                real = path.resolve()
                if tmpdir.resolve() in real.parents and real.is_file():
                    shutil.copy2(real, dest / path.name)
                    kept.append(path.name)
    return kept


def pe_imports(path: Path) -> list[str]:
    """PE 파일의 import DLL 이름(지연 로드 제외). 외부 도구 없이 헤더만 읽는다."""
    data = path.read_bytes()
    if data[:2] != b"MZ":
        return []
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        return []
    sections_count = struct.unpack_from("<H", data, pe + 6)[0]
    opt_size = struct.unpack_from("<H", data, pe + 20)[0]
    opt = pe + 24
    magic = struct.unpack_from("<H", data, opt)[0]
    dirs = opt + (112 if magic == 0x20B else 96)
    import_rva = struct.unpack_from("<I", data, dirs + 8)[0]
    sections = [struct.unpack_from("<8sIIII", data, opt + opt_size + 40 * i) for i in range(sections_count)]

    def offset(rva: int) -> int:
        for _name, vsize, vaddr, rsize, raw in sections:
            if vaddr <= rva < vaddr + max(vsize, rsize):
                return rva - vaddr + raw
        raise ValueError(f"{path.name}: RVA {rva:#x}가 어느 구역에도 없어요")

    names, pos = [], offset(import_rva) if import_rva else None
    while pos is not None:
        name_rva = struct.unpack_from("<I", data, pos + 12)[0]
        if name_rva == 0:
            break
        start = offset(name_rva)
        names.append(data[start:data.index(b"\0", start)].decode("ascii"))
        pos += 20
    return names


def check_imports(llama_dir: Path) -> list[str]:
    """서버 폴더의 실행 파일과 DLL이 부르는 DLL 중 폴더 안에도, Windows 기본에도 없는 것."""
    present = {p.name.lower() for p in llama_dir.iterdir()}
    missing = set()
    for path in llama_dir.iterdir():
        if path.suffix.lower() not in {".exe", ".dll"}:
            continue
        for name in pe_imports(path):
            low = name.lower()
            if low in present or low in SYSTEM_DLLS or low.startswith(("api-ms-win-", "ext-ms-win-")):
                continue
            missing.add(f"{path.name} → {name}")
    return sorted(missing)


def build(platform: str, out: Path, cache: Path, crt_dir: Path | None = None) -> dict:
    src = json.loads(SOURCES.read_text(encoding="utf-8"))
    llama = src["llama_cpp"]
    if platform not in llama["platforms"]:
        raise SystemExit(f"지원하지 않는 플랫폼이에요: {platform} (가능: {', '.join(llama['platforms'])})")
    plat = llama["platforms"][platform]
    model = src["model"]

    archive = fetch(plat["url"], plat["sha256"], cache)
    gguf = fetch(model["url"], model["sha256"], cache)
    llama_license = fetch(llama["license"]["url"], llama["license"]["sha256"], cache)
    model_license = fetch(model["license"]["url"], model["license"]["sha256"], cache)
    if gguf.stat().st_size != model["size"]:
        raise SystemExit("모델 파일 크기가 sources.json과 달라요")

    if out.exists():
        shutil.rmtree(out)
    windows = platform.startswith("windows")
    if windows and crt_dir is None:
        raise SystemExit("Windows 팩에는 MSVC 런타임이 필요해요. --crt-dir로 VC 재배포 x64 폴더를 지정해 주세요.")
    kept = extract_server(archive, plat["keep"], out / "llama")
    if plat["server"] not in kept:
        shutil.rmtree(out)
        raise SystemExit(f"압축 안에 {plat['server']}가 없어요")
    if windows:
        for name in CRT_DLLS:
            source = next((p for p in crt_dir.iterdir() if p.name.lower() == name), None)
            if source is None:
                shutil.rmtree(out)
                raise SystemExit(f"--crt-dir에 {name}이 없어요: {crt_dir}")
            shutil.copy2(source, out / "llama" / source.name)
        missing = check_imports(out / "llama")
        if missing:
            shutil.rmtree(out)
            raise SystemExit("팩 안에서 찾을 수 없는 DLL이 있어요:\n  " + "\n  ".join(missing))
    (out / "models").mkdir(parents=True)
    shutil.copy2(gguf, out / "models" / model["file"])
    lic = out / "licenses"
    lic.mkdir()
    shutil.copy2(llama_license, lic / "llama.cpp-LICENSE.txt")
    shutil.copy2(model_license, lic / "Qwen3-LICENSE.txt")
    omp = out / "llama" / "LICENSE-LLVM-OpenMP"
    if omp.exists():
        omp.replace(lic / "LLVM-OpenMP-LICENSE.txt")

    manifest = {
        "format": 1,
        "name": src["name"],
        "model": f"models/{model['file']}",
        "model_size": model["size"],
        "model_sha256": model["sha256"],
        "model_source": model["url"],
        "server": f"llama/{plat['server']}",
        "llama_cpp": llama["build"],
        "llama_cpp_commit": llama["commit"],
        "platform": platform,
    }
    (out / "ai-pack.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "README.txt").write_text(
        "한 장 제주 오프라인 AI 팩\r\n\r\n"
        f"- 모델: {src['name']} ({model['file']}), 원본 {model['base_model']}, Apache-2.0\r\n"
        f"- 서버: llama.cpp {llama['build']} ({llama['commit'][:9]}), MIT\r\n"
        "- 한 장 제주가 켜질 때 이 폴더를 찾아 이 PC(127.0.0.1)에서만 모델 서버를 실행합니다. 인터넷에 연결하지 않습니다.\r\n"
        "- 라이선스 전문: licenses 폴더\r\n",
        encoding="utf-8",
    )
    return manifest


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("platform", help="windows-x64, macos-arm64, macos-x64")
    parser.add_argument("--out", type=Path, default=ROOT / "output/ai-pack")
    parser.add_argument("--cache", type=Path, default=ROOT / "output/ai-pack-cache")
    parser.add_argument("--crt-dir", type=Path, help="Windows: vcruntime140.dll, vcruntime140_1.dll, msvcp140.dll이 있는 VC 재배포 x64 폴더")
    args = parser.parse_args(argv)
    manifest = build(args.platform, args.out, args.cache, args.crt_dir)
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
