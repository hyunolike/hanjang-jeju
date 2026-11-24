"""로컬 원본의 품질 집계와 제한된 셀 예시. 원본/결과를 저장하지 않는다."""
from __future__ import annotations

import csv
import io
import math

import pandas as pd

from . import aggregate, ingest, semantics

KINDS = ("missing", "none", "masked", "trimmed", "subtotal", "subtotal_candidate", "invalid_date", "invalid_number")
MESSAGES = {
    "missing": "빈 값이에요. 0으로 채우지 않아요.",
    "none": "값 없음 표시예요. 0과 구분해요.",
    "masked": "가려진 값이에요. 알 수 없음으로 두어요.",
    "trimmed": "공백을 정리했어요.",
    "subtotal": "같은 묶음의 상세 행이 있어 소계를 따로 뒀어요.",
    "subtotal_candidate": "소계 표기가 있지만 같은 기간·묶음의 상세를 확인하지 못해 유지했어요.",
    "invalid_date": "월별 날짜로 읽지 못했어요. 기준 날짜나 원본을 확인해 주세요.",
    "invalid_number": "유한한 숫자로 읽지 못했어요. 값 항목이나 원본을 확인해 주세요.",
}


def inspect(raw: bytes, *, time: str | None = None, value: str | None = None,
            kind: str | None = None, column: str | None = None,
            offset: int = 0, limit: int = 50) -> dict:
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("표시할 행 범위를 확인해 주세요.")
    if kind is not None and kind not in KINDS:
        raise ValueError("지원하지 않는 품질 항목이에요.")
    encoding = ingest.detect_encoding(raw)
    reader = csv.reader(io.StringIO(raw.decode(encoding)), strict=True)
    physical_lines = io.StringIO(raw.decode(encoding), newline='').readlines()
    error = None
    rows: list[list[str]] = []
    lines: list[tuple[int, int]] = []
    header: list[str] = []
    try:
        header = [ingest.INVISIBLE_SPACE.sub("", x).strip() for x in next(reader)]
        if not header or any(not x for x in header) or len(set(header)) != len(header):
            raise ValueError("열 이름에 빈칸이나 중복이 있어요.")
        for selected in (time, value, column):
            if selected is not None and selected not in header:
                raise ValueError(f"‘{selected}’ 항목을 이 자료에서 찾지 못했어요.")
        previous = reader.line_num
        for row in reader:
            start, end = previous + 1, reader.line_num
            previous = end
            if ingest.blank_record(row, start, end, physical_lines):
                continue
            if len(row) != len(header):
                error = {"line": start, "message": "칸 수가 열 이름 수와 달라 뒤의 행을 검사하지 못했어요."}
                break
            rows.append(row)
            lines.append((start, end))
    except (StopIteration, csv.Error):
        error = {"line": max(reader.line_num, 1), "message": "CSV 구조를 끝까지 읽지 못했어요."}

    frame = pd.DataFrame(rows, columns=header, dtype=str)
    clean = ingest.clean(frame, encoding)
    kept = {x - 2 for x in clean.source_rows}
    counts = dict.fromkeys(KINDS, 0)
    columns = {name: dict.fromkeys(KINDS, 0) for name in header}
    issues: list[dict] = []
    matched = affected = 0

    def add(event_kind, name, before, after, line, line_end):
        nonlocal matched
        counts[event_kind] += 1
        if name is not None:
            columns[name][event_kind] += 1
        if (kind is not None and kind != event_kind) or (column is not None and column != name):
            return
        matched += 1
        if not offset < matched <= offset + limit:
            return
        truncated = any(isinstance(x, str) and len(x) > 200 for x in (before, after))
        issues.append({"kind": event_kind, "column": name, "line": line, "line_end": line_end,
                       "before": before[:200] if isinstance(before, str) else before,
                       "after": after[:200] if isinstance(after, str) else after,
                       "truncated": truncated, "message": MESSAGES[event_kind]})

    for index, row in enumerate(rows):
        line, line_end = lines[index]
        had_issue = False
        subtotal_column = None
        normalized = dict(zip(header, map(ingest.normalize_text, row)))
        for name, original in zip(header, row):
            text = normalized[name]
            if original != text:
                add("trimmed", name, original, text, line, line_end)
                had_issue = True
            state = "missing" if text in ingest.MISSING_TOKENS else "none" if text in ingest.NONE_TOKENS else "masked" if ingest.MASK_PATTERN.fullmatch(text) else None
            if state:
                add(state, name, original, None, line, line_end)
                had_issue = True
            if text in ingest.SUBTOTAL_TOKENS and semantics.value_semantic(name).role != "measure":
                subtotal_column = subtotal_column or name
            if index in kept:
                if name == time and aggregate.parse_month(text) is None:
                    add("invalid_date", name, original, None, line, line_end)
                    had_issue = True
                if name == value and not state:
                    number = pd.to_numeric(text, errors="coerce")
                    if not math.isfinite(float(number)):
                        add("invalid_number", name, original, None, line, line_end)
                        had_issue = True
        if index not in kept:
            add("subtotal", subtotal_column, normalized.get(subtotal_column), None, line, line_end)
            had_issue = True
        elif subtotal_column:
            add("subtotal_candidate", subtotal_column, normalized[subtotal_column], normalized[subtotal_column], line, line_end)
            had_issue = True
        affected += had_issue
    return {"complete": error is None, "error": error, "encoding": encoding,
            "rows": len(rows), "clean_rows": len(clean.data), "affected_rows": affected,
            "counts": counts, "columns": [{"name": k, "counts": v} for k, v in columns.items()],
            "matched_issues": matched, "offset": offset, "limit": limit, "issues": issues}
