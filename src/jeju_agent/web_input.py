"""공개 웹의 요청별 CSV 검사. 원본을 작업 폴더에 저장하지 않는다."""
from __future__ import annotations

import csv
import hashlib
import io
import math
import re
from pathlib import Path
from typing import Literal

import pandas as pd
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import aggregate, ingest, pipeline, semantics

MAX_BYTES = 3 * 1024 * 1024
MAX_ROWS = 20_000
MAX_COLUMNS = 50


class Filter(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    column: str = Field(min_length=1, max_length=200)
    values: list[str] = Field(min_length=1, max_length=50)


class ExecutionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    time: str = Field(min_length=1, max_length=200)
    value: str = Field(min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=200)
    unit: str = Field(default="", max_length=20)
    additive_confirmed: bool = False
    intent: Literal["overview", "compare", "share", "rank", "forecast"] = "overview"
    filters: list[Filter] = Field(default_factory=list, max_length=2)
    period_n: int = Field(default=0, ge=0, le=36)
    horizon: int = Field(default=6, ge=1, le=12)
    run_forecast: bool = False
    tools: list[str] = Field(default_factory=list)
    business_task: Literal["quarter_compare", "category_change", "brief"] | None = None
    plan_origin: Literal["model", "recipe"] | None = None

    @model_validator(mode="after")
    def validate_tools(self):
        if self.business_task:
            if self.plan_origin is None or self.intent != "overview" or self.period_n or self.run_forecast:
                raise ValueError("업무 분석의 종류와 실행 조건을 확인해 주세요")
            expected = ["quarter_compare"]
            if self.business_task != "quarter_compare":
                expected.append("category_change")
            if self.business_task == "brief":
                expected.append("brief")
            if self.tools and self.tools != expected:
                raise ValueError("허용되지 않은 업무 도구예요")
            self.tools = expected
            return self
        if self.plan_origin is not None:
            raise ValueError("업무 분석에만 계획 출처를 지정할 수 있어요")
        expected = ["overview"]
        if self.intent in {"compare", "share", "rank"}:
            expected.append(self.intent)
        if self.intent == "forecast" and not self.run_forecast:
            raise ValueError("예측 도구 확인이 필요해요")
        if self.run_forecast:
            expected.append("forecast")
        if self.tools and self.tools != expected:
            raise ValueError("허용되지 않은 도구예요")
        self.tools = expected
        return self


def reject(message: str, status: int = 422):
    raise HTTPException(status, message)


class SelectionError(HTTPException):
    def __init__(self, message: str, field: str, code: str, column: str = "", row: int | None = None, status: int = 422):
        super().__init__(status, message)
        self.issue = {"field": field, "code": code, "column": column}
        if row is not None:
            self.issue["row"] = row


def parse_month(value: str) -> str | None:
    return aggregate.parse_month(value)


def strict_month(value: str, row: int, column: str = "") -> str:
    month = parse_month(value)
    if month is None:
        raise SelectionError(f"‘{column or '날짜'}’의 {row}행을 날짜로 읽지 못했어요. 202401 또는 2024-01-01처럼 연도와 월이 있는 항목을 골라 주세요.", "time", "invalid_date", column, row)
    return month


def value_semantic(name: str, ko: str = "") -> semantics.Semantic:
    return semantics.value_semantic(name, ko)

def dataset(raw: bytes, filename: str, spec: ExecutionSpec | None = None, *, enforce_limits: bool = True) -> pipeline.Dataset:
    if enforce_limits and len(raw) > MAX_BYTES:
        reject("CSV는 3MiB 이하로 넣어 주세요.", 413)
    if not filename.lower().endswith(".csv"):
        reject("CSV 파일만 넣을 수 있어요.")
    try:
        encoding = ingest.detect_encoding(raw)
        decoded = raw.decode(encoding)
        if not decoded.strip():
            reject("파일이 비어 있어요. 데이터가 있는 CSV를 넣어 주세요.")
        reader = csv.reader(io.StringIO(decoded), strict=True)
        header = next(reader)
        header = [ingest.INVISIBLE_SPACE.sub("", x).strip() for x in header]
        if not header or any(not x or len(x) > 200 for x in header) or len(set(header)) != len(header):
            reject("열 이름에 빈칸이나 중복이 있어요. 서로 다른 열 이름을 넣어 주세요.")
        if enforce_limits and len(header) > MAX_COLUMNS:
            reject("한 번에 50열까지 분석할 수 있어요.", 413)
        count = 0
        for row in reader:
            if not row:
                continue
            count += 1
            if enforce_limits and count > MAX_ROWS:
                reject("한 번에 20,000행까지 분석할 수 있어요.", 413)
            if len(row) != len(header):
                reject(f"{reader.line_num}행의 칸 수가 열 이름 수와 달라요.")
        if not count:
            reject("분석할 데이터 행이 없어요.")
        clean = ingest.load_bytes(raw)
    except (StopIteration, UnicodeError, csv.Error, ValueError, pd.errors.ParserError):
        reject("CSV 형식이나 인코딩을 읽지 못했어요. UTF-8 또는 CP949 CSV로 다시 저장해 주세요.")
    if clean.data.empty:
        reject("정리한 뒤 분석할 행이 없어요.")
    selected = None
    if spec is not None:
        selected = spec.model_dump()
        names = [spec.time, spec.value] + ([spec.category] if spec.category else [])
        if len(names) != len(set(names)) or any(n not in clean.data.columns for n in names):
            reject("날짜, 값, 분류는 자료에 있는 서로 다른 열로 골라 주세요.")
        value_meaning = value_semantic(spec.value)
        if value_meaning.role in {"time", "region", "category"}:
            raise SelectionError(f"‘{spec.value}’은 금액이나 수량이 아닌 항목이에요. 분석할 숫자를 다시 골라 주세요.", "value", "not_measure", spec.value)
        if not spec.additive_confirmed or value_meaning.additive is False:
            raise SelectionError("금액이나 건수처럼 합계를 낼 수 있는 항목을 골라 주세요. 평균과 비율은 더할 수 없어요.", "value", "not_additive", spec.value)
        months = [strict_month(str(v) if pd.notna(v) else "", row, spec.time) for row, v in zip(clean.source_rows, clean.data[spec.time])]
        periods = pd.PeriodIndex(months, freq="M")
        if periods.max().ordinal - periods.min().ordinal + 1 > 1200:
            raise SelectionError("날짜 범위가 너무 넓어요. 100년 이내의 자료를 넣어 주세요.", "time", "date_span", spec.time, status=413)
        numeric = pd.to_numeric(clean.data[spec.value], errors="coerce")
        for row, original, value in zip(clean.source_rows, clean.data[spec.value], numeric):
            if pd.isna(original):
                continue
            try:
                if not math.isfinite(float(value)):
                    raise ValueError
            except (ValueError, TypeError, OverflowError):
                raise SelectionError(f"‘{spec.value}’의 {row}행을 숫자로 읽지 못했어요. 다른 숫자 항목을 고르거나 CSV의 해당 값을 확인해 주세요.", "value", "invalid_number", spec.value, row)
        if numeric.notna().sum() == 0:
            raise SelectionError("이 항목에는 분석할 숫자가 없어요. 금액이나 건수가 있는 항목을 골라 주세요.", "value", "empty_number", spec.value)
        clean.data[spec.time] = months
        if spec.intent in {"share", "rank"} and not spec.category:
            reject("비중과 순위는 나눠 볼 분류 열을 골라 주세요.")
        for f in spec.filters:
            if f.column != spec.category:
                reject("고른 분류 열로만 거를 수 있어요.")
            actual = set(clean.data[f.column].dropna().astype(str))
            if not set(f.values) <= actual:
                reject("자료에 없는 값으로 거를 수 없어요.")
    identity = hashlib.sha256(raw).hexdigest()[:24]
    return pipeline.Dataset("web-" + identity, Path(filename).name[:120], "upload", Path("unused"), data=clean, selection=selected)
