"""사실 저장소 (요구사항 A02, G03, 기획안 13.2).

계산 결과는 모두 사실 ID를 가진다. 모델이 쓴 문장은 사실 ID를 인용해야 하고,
문장 속 숫자는 인용한 사실과 대조된다. 사실에 없는 숫자는 화면에 나가지 않는다.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import asdict, dataclass, field

NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


@dataclass(frozen=True)
class Fact:
    id: str
    kind: str
    value: float
    unit: str = ""
    label: str = ""
    basis: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class FactStore:
    def __init__(self) -> None:
        self._facts: dict[str, Fact] = {}
        self._seq = itertools.count(1)

    def add(self, kind: str, value: float, unit: str = "", label: str = "", **basis) -> Fact:
        fact = Fact(f"F{next(self._seq):03d}", kind, float(value), unit, label, basis)
        self._facts[fact.id] = fact
        return fact

    def get(self, fact_id: str) -> Fact:
        return self._facts[fact_id]

    def all(self) -> list[Fact]:
        return list(self._facts.values())


def numbers_in(text: str) -> list[float]:
    return [float(m.replace(",", "")) for m in NUMBER.findall(text)]


def sentence_matches_facts(text: str, facts: list[Fact]) -> bool:
    """문장 속 모든 숫자가 인용한 사실의 값과 맞는지 본다.

    소수 첫째 자리 반올림(±0.05)까지 허용한다. 연월처럼 사실의 근거(basis)에 든 숫자도 허용한다.
    """
    allowed: list[float] = []
    for fact in facts:
        allowed += [fact.value, round(fact.value, 1), float(round(fact.value))]
        for value in fact.basis.values():
            allowed.extend(numbers_in(str(value)))
    return all(
        any(abs(number - a) <= 0.051 for a in allowed) for number in numbers_in(text)
    )
