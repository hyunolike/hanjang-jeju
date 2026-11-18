"""CSV 읽기와 정리 (요구사항 D01, D04, D05, D06, D08).

정리 원칙
- 원본 값을 바꿔 지어내지 않는다. 특수값은 결측(NaN)으로 바꾸되, 무엇이었는지를 상태 표(`status`)에 남긴다.
- 가림 기호(`*`, `**` 등)는 "값 없음"과 다르다. 합계에 0으로 들어가면 안 되므로 상태를 "masked"로 둔다.
- 소계와 합계 행은 지우지 않고 따로 떼어 둔다. 그대로 더하면 두 번 세기 때문이다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

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
    encoding = detect_encoding(raw)
    frame = pd.read_csv(
        Path(path), encoding=encoding, dtype=str, keep_default_na=False
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

    text_columns = [c for c in data.columns if not _mostly_numeric(data[c])]
    subtotal_mask = pd.Series(False, index=data.index)
    for column in text_columns:
        is_token = data[column].isin(SUBTOTAL_TOKENS)
        if not is_token.any():
            continue
        # '소계'가 소계인 것은 같은 묶음(다른 글자 열이 같은 행들)에 세부 행이 함께 있을 때뿐이다.
        # 세부 없이 '소계'만 있는 묶음(예: 활동사업체의 생멸구분)은 그 행이 곧 값이므로 남긴다.
        keys = [c for c in text_columns if c != column]
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
    )


def _mostly_numeric(series: pd.Series) -> bool:
    values = series.dropna()
    if values.empty:
        return False
    return pd.to_numeric(values, errors="coerce").notna().mean() > 0.9


def load(path: str | Path) -> CleanResult:
    frame, encoding = read_csv(path)
    return clean(frame, encoding)
