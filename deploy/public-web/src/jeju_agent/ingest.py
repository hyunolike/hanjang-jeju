"""CSV 읽기와 정리 (요구사항 D01, D04, D05, D06, D08).

정리 원칙
- 원본 값을 바꿔 지어내지 않는다. 특수값은 결측(NaN)으로 바꾸되, 무엇이었는지를 상태 표(`status`)에 남긴다.
- 가림 기호(`*`, `**` 등)는 "값 없음"과 다르다. 합계에 0으로 들어가면 안 되므로 상태를 "masked"로 둔다.
- 소계와 합계 행은 지우지 않고 따로 떼어 둔다. 그대로 더하면 두 번 세기 때문이다.
"""

from __future__ import annotations

import re
import csv
import hashlib
from io import BytesIO, StringIO
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import aggregate, semantics

ENCODINGS = ("utf-8-sig", "cp949")
MISSING_TOKENS = {"", "NULL", "null", "NA", "N/A", "nan", "NaN", "None"}
NONE_TOKENS = {"-"}
MASK_PATTERN = re.compile(r"^\*+$")
SUBTOTAL_TOKENS = {"소계", "합계", "총계", "전체", "계"}
INVISIBLE_SPACE = re.compile(r"[  -​　﻿]")


@dataclass
class ColumnReport:
    missing: int = 0
    none: int = 0
    masked: int = 0
    trimmed: int = 0


@dataclass
class CleanResult:
    data: pd.DataFrame
    status: pd.DataFrame
    subtotals: pd.DataFrame
    encoding: str
    columns: dict[str, ColumnReport] = field(default_factory=dict)
    source_rows: list[int] = field(default_factory=list)
    source_sha256: str | None = None
    source_bytes: int | None = None

    def report(self) -> dict:
        return {
            "encoding": self.encoding,
            "rows": int(len(self.data)),
            "subtotal_rows": int(len(self.subtotals)),
            "columns": {
                name: vars(rep)
                for name, rep in self.columns.items()
                if any(vars(rep).values())
            },
        }


def detect_encoding(raw: bytes) -> str:
    for encoding in ENCODINGS:
        try:
            raw.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            continue
    raise ValueError("지원하지 않는 인코딩이에요. 센터 화면에서 UTF-8 CSV로 다시 받아 주세요.")


def read_csv(path: str | Path) -> tuple[pd.DataFrame, str]:
    raw = Path(path).read_bytes()
    return read_bytes(raw)


def read_bytes(raw: bytes) -> tuple[pd.DataFrame, str]:
    encoding = detect_encoding(raw)
    frame = pd.read_csv(
        BytesIO(raw), encoding=encoding, dtype=str, keep_default_na=False
    )
    frame.columns = [INVISIBLE_SPACE.sub("", c).strip() for c in frame.columns]
    return frame, encoding


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", INVISIBLE_SPACE.sub(" ", value)).strip()


def clean(frame: pd.DataFrame, encoding: str = "") -> CleanResult:
    data = frame.copy()
    status = pd.DataFrame("ok", index=data.index, columns=data.columns)
    reports: dict[str, ColumnReport] = {}
    for column in data.columns:
        rep = ColumnReport()
        original = data[column].astype(str)
        normalized = original.map(normalize_text)
        rep.trimmed = int((normalized != original).sum())
        is_missing = normalized.isin(MISSING_TOKENS)
        is_none = normalized.isin(NONE_TOKENS)
        is_masked = normalized.str.fullmatch(MASK_PATTERN.pattern)
        rep.missing, rep.none, rep.masked = (
            int(is_missing.sum()),
            int(is_none.sum()),
            int(is_masked.sum()),
        )
        status.loc[is_missing, column] = "missing"
        status.loc[is_none, column] = "none"
        status.loc[is_masked, column] = "masked"
        data[column] = normalized.where(~(is_missing | is_none | is_masked))
        reports[column] = rep

    roles = {c: semantics.value_semantic(c).role for c in data.columns}
    text_columns = [c for c in data.columns if roles[c] != "measure" and not _mostly_numeric(data[c])]
    # 숫자로 쓰인 날짜/지역/분류도 묶음 키다. 다른 달이나 다른 지역의 상세 행은
    # 이 행이 소계라는 근거가 되지 않는다. 알 수 없는 기간 열도 보수적으로 보존한다.
    group_columns = [c for c in data.columns if roles[c] in {"time", "region", "category"} or (roles[c] != "measure" and re.search(r'date|time|period|year|기간|시점|날짜|연월|년월|연도', c, re.I) and _looks_like_period(data[c]))]
    subtotal_mask = pd.Series(False, index=data.index)
    for column in text_columns:
        is_token = data[column].isin(SUBTOTAL_TOKENS)
        if not is_token.any():
            continue
        # '소계'가 소계인 것은 같은 묶음(다른 글자 열이 같은 행들)에 세부 행이 함께 있을 때뿐이다.
        # 세부 없이 '소계'만 있는 묶음(예: 활동사업체의 생멸구분)은 그 행이 곧 값이므로 남긴다.
        keys = [c for c in dict.fromkeys([*text_columns, *group_columns]) if c != column]
        if keys:
            has_detail = (~is_token).groupby([data[k].fillna("") for k in keys]).transform("any")
            is_token &= has_detail
        subtotal_mask |= is_token
    return CleanResult(
        data=data[~subtotal_mask].reset_index(drop=True),
        status=status[~subtotal_mask].reset_index(drop=True),
        subtotals=data[subtotal_mask].reset_index(drop=True),
        encoding=encoding,
        columns=reports,
        source_rows=[i + 2 for i, subtotal in enumerate(subtotal_mask) if not subtotal],
    )


def _mostly_numeric(series: pd.Series) -> bool:
    values = series.dropna()
    if values.empty:
        return False
    return pd.to_numeric(values, errors="coerce").notna().mean() > 0.9


def _looks_like_period(series: pd.Series) -> bool:
    values = series.dropna().astype(str)
    return not values.empty and all(re.fullmatch(r"[12]\d{3}", v) or aggregate.parse_month(v) is not None for v in values)


def load(path: str | Path) -> CleanResult:
    return load_bytes(Path(path).read_bytes())


def load_bytes(raw: bytes) -> CleanResult:
    frame, encoding = read_bytes(raw)
    result = clean(frame, encoding)
    result.source_sha256 = hashlib.sha256(raw).hexdigest()
    result.source_bytes = len(raw)
    reader = csv.reader(StringIO(raw.decode(encoding)), strict=True)
    physical_lines = StringIO(raw.decode(encoding), newline='').readlines()
    next(reader)
    source_lines = []
    previous = reader.line_num
    for row in reader:
        start = previous + 1
        previous = reader.line_num
        if not blank_record(row, start, reader.line_num, physical_lines):
            source_lines.append(start)
    result.source_rows = [source_lines[row - 2] for row in result.source_rows]
    return result


def blank_record(row: list[str], start: int, end: int, physical_lines: list[str]) -> bool:
    """물리적인 빈 줄만 건너뛰고 따옴표로 감싼 빈 셀은 보존한다."""
    return not row or not ''.join(physical_lines[start - 1:end]).strip()
