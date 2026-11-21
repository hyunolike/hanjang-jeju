"""법정동-행정동 대응과 결합 커버리지 (요구사항 J01, J02, J03).

대응표는 제주데이터허브의 '제주특별자치도 상가(상권) 정보'에서 만든다. 한 행에 행정동 코드(8자리)와
법정동 코드(10자리)가 함께 들어 있다. 법정동 10자리는 시도 2, 시군구 3, 읍면동 3, 리 2자리이므로
앞 8자리가 센터 명세의 8자리 법정동 코드(예: 1-19 bjd_cd)와 같다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

CITY_PREFIX = re.compile(r"^(제주특별자치도\s*)?(제주시|서귀포시)\s*")


def normalize_region_name(name: str) -> str:
    return CITY_PREFIX.sub("", str(name).strip()).replace(" ", "")


def normalize_code(code: str | int | float) -> str:
    """지역 코드를 8자리 문자열로 맞춘다. 10자리 법정동 코드는 리 단위를 버린다."""
    digits = re.sub(r"\D", "", str(code).split(".")[0])
    if len(digits) >= 10:
        return digits[:8]
    return digits.ljust(8, "0")[:8]


def region_map(stores: pd.DataFrame) -> pd.DataFrame:
    """상가 정보에서 법정동(8자리)-행정동 대응 쌍을 만든다."""
    pairs = stores[["행정동코드", "행정동명", "법정동코드", "법정동명"]].dropna().drop_duplicates()
    out = pd.DataFrame(
        {
            "emd_cd": pairs["행정동코드"].map(normalize_code),
            "emd_nm": pairs["행정동명"].map(normalize_region_name),
            "bjd_cd": pairs["법정동코드"].map(normalize_code),
            "bjd_cd10": pairs["법정동코드"].str.strip(),
            "bjd_nm": pairs["법정동명"].map(normalize_region_name),
        }
    )
    return out.drop_duplicates().reset_index(drop=True)


@dataclass
class JoinReport:
    left_rows: int
    matched_rows: int
    unmatched_rows: int
    unmatched_keys: list
    multi_match_keys: list

    def to_dict(self) -> dict:
        return vars(self)


def join_with_report(
    left: pd.DataFrame, right: pd.DataFrame, on: list[str], how: str = "left"
) -> tuple[pd.DataFrame, JoinReport]:
    """결합하고, 붙지 않은 키와 여러 짝이 붙은 키를 함께 돌려준다.

    내부 결합은 짝 없는 행을 조용히 버리므로 기본은 왼쪽 결합이다(기획안 13.4).
    """
    counts = right.groupby(on).size()
    multi = counts[counts > 1]
    merged = left.merge(right, on=on, how=how, indicator=True)
    unmatched = merged[merged["_merge"] == "left_only"]
    report = JoinReport(
        left_rows=int(len(left)),
        matched_rows=int((merged["_merge"] == "both").sum()),
        unmatched_rows=int(len(unmatched)),
        unmatched_keys=sorted(map(_key, unmatched[on].drop_duplicates().itertuples(index=False))),
        multi_match_keys=sorted(map(_key, multi.index.to_frame(index=False).itertuples(index=False))),
    )
    return merged.drop(columns="_merge"), report


def _key(row) -> str | tuple:
    values = tuple(row)
    return values[0] if len(values) == 1 else values
