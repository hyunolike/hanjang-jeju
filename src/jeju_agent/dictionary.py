"""표 사전과 표 인식 (요구사항 D02, D03).

두 출처의 표를 한 사전에 둔다.
- center: 공개 데이터 명세서의 센터 표 71종 (data/reference/center_spec.json)
- hub: 제주데이터허브 공개 자료 (data/reference/hub_tables.json)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache

from .paths import REFERENCE

# 센터 화면에서 받을 때 빠질 수 있는 파티션 열. 인식 점수에서 뺀다.
PARTITION_COLUMNS = {"pt_year", "pt_month"}


@dataclass(frozen=True)
class Table:
    id: str
    source: str
    title: str
    columns: tuple[dict, ...]

    @property
    def names(self) -> frozenset[str]:
        return frozenset(c["name"] for c in self.columns)

    def column(self, name: str) -> dict | None:
        return next((c for c in self.columns if c["name"] == name), None)


@lru_cache(maxsize=1)
def tables() -> tuple[Table, ...]:
    center = json.loads((REFERENCE / "center_spec.json").read_text(encoding="utf-8"))
    hub = json.loads((REFERENCE / "hub_tables.json").read_text(encoding="utf-8"))
    out = [
        Table(id=t["id"], source="center", title=t["title"], columns=tuple(t["columns"]))
        for t in center["tables"].values()
    ]
    out += [
        Table(id=t["id"], source="hub", title=t["title"], columns=tuple(t["columns"]))
        for t in hub["tables"]
    ]
    return tuple(out)


def table(table_id: str) -> Table:
    return next(t for t in tables() if t.id == table_id)


@dataclass(frozen=True)
class Recognition:
    table: Table | None
    score: float
    candidates: tuple[tuple[str, float], ...]
    unknown_columns: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "table_id": self.table.id if self.table else None,
            "title": self.table.title if self.table else None,
            "source": self.table.source if self.table else None,
            "score": round(self.score, 3),
            "candidates": [{"table_id": i, "score": round(s, 3)} for i, s in self.candidates],
            "unknown_columns": list(self.unknown_columns),
        }


def recognize(columns: list[str], threshold: float = 0.8) -> Recognition:
    """열 집합이 가장 잘 맞는 표를 찾는다.

    점수는 두 방향의 겹침을 곱한다. 받은 열이 표에 얼마나 들어 있는지(정밀도)와
    표의 열(파티션 제외)이 받은 파일에 얼마나 있는지(재현율)를 함께 본다.
    이용자가 센터 화면에서 일부 열만 골라 받을 수 있으므로 재현율은 제곱근으로 완만하게 반영한다.
    """
    given = {c.strip() for c in columns if c.strip()}
    scored = []
    for t in tables():
        expected = t.names - PARTITION_COLUMNS
        if not expected:
            continue
        overlap = len(given & t.names)
        precision = overlap / len(given)
        recall = len(given & expected) / len(expected)
        scored.append((t, precision * recall**0.5))
    scored.sort(key=lambda item: (-item[1], len(item[0].names)))
    best, score = scored[0]
    candidates = tuple((t.id, s) for t, s in scored[:3] if s > 0)
    if score < threshold:
        return Recognition(None, score, candidates, tuple(sorted(given)))
    return Recognition(best, score, candidates, tuple(sorted(given - best.names)))
