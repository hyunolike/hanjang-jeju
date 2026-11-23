"""열의 의미 유형, 단위, 합산 가능 여부 (요구사항 D07, 기획안 13.1 의미 계층).

규칙은 열 이름과 명세서의 한글명에서 정한다. 규칙에 걸리지 않는 열은 "unknown"으로 두고
이용자에게 뜻을 묻는다. 추측으로 숫자 열을 측정값으로 단정하지 않는다.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

TIME = re.compile(r"(^base_(year_month|date)$|^pt_(year|month)$|^(base_)?date$|year|month|연월|기준연도|년월|날짜|일자)", re.I)
REGION = re.compile(r"(emd|bjd|eupmyeondong|city|province|dstrct|sido|gungu|grid|zip|읍면동|행정동|법정동|시구분|시군구|시도명)", re.I)
NON_ADDITIVE = re.compile(r"(per_person|per_case|unit_price|rate|ratio|avg|average|평균|단가|비율|률)", re.I)
MEASURE = re.compile(r"(cnt|count|amt|amount|amout|sale|cost|pop|rainfall|temperature|speed|수$|금액|매출|인구|건수)", re.I)


@dataclass(frozen=True)
class Semantic:
    role: str  # time | region | category | measure | unknown
    unit: str = ""
    additive: bool | None = None
    note: str = ""


def infer(name: str, ko: str = "") -> Semantic:
    text = f"{name} {ko}"
    if NON_ADDITIVE.search(text):
        return Semantic("measure", _unit(name, ko), False, "평균이나 비율이라 더하지 않는다")
    if TIME.search(name) or TIME.search(ko):
        return Semantic("time")
    if MEASURE.search(name) or MEASURE.search(ko):
        return _measure(name, ko)
    if REGION.search(name) or REGION.search(ko):
        return Semantic("region")
    if name.endswith(("_nm", "_cd", "_type", "_gb")) or ko.endswith(("명", "코드", "구분")):
        return Semantic("category")
    if name in {"sex", "age", "age_range", "time", "time_type", "time_range", "week", "성별", "연령대"}:
        return Semantic("category")
    return Semantic("unknown")


def _measure(name: str, ko: str) -> Semantic:
    unit = _unit(name, ko)
    note = ""
    if ko == "표본수":
        note = "매장 수가 아니라 표본 매장 수다. 매장당 값은 표본 평균이다"
    if re.search(r"user_?c(ou)?nt|이용자수", f"{name} {ko}", re.I):
        return Semantic("measure", unit, False, "같은 사람이 여러 행에 잡힐 수 있어 더하지 않는다(명세로 확인 필요)")
    if re.search(r"pop", name, re.I) or "인구" in ko:
        return Semantic("measure", unit, False, "시각마다 잰 인구라 시간대끼리 더하면 연인원이 된다")
    if re.search(r"temperature|speed", name, re.I):
        return Semantic("measure", unit, False, "")
    return Semantic("measure", unit, True, note)


def _unit(name: str, ko: str) -> str:
    text = f"{name} {ko}"
    if re.search(r"by_million|백만", text, re.I):
        return "백만 원"
    if re.search(r"amt|amount|amout|cost|sale|금액|매출|단가", text, re.I):
        return "원"
    if re.search(r"pop|인구|user|이용자|visit", text, re.I):
        return "명"
    if re.search(r"rainfall|강수", text, re.I):
        return "mm"
    if re.search(r"temperature|기온", text, re.I):
        return "℃"
    if re.search(r"cnt|count|건수|수$", text, re.I):
        return "건"
    return ""


def describe(columns: list[dict]) -> dict[str, dict]:
    return {c["name"]: asdict(infer(c["name"], c.get("ko", ""))) for c in columns}


def value_semantic(name: str, ko: str = "") -> Semantic:
    """입력의 명시적 단위를 보존한다. 숫자 모양만으로 합산을 확정하지 않는다."""
    sem = infer(re.sub(r"\s+", "", name), re.sub(r"\s+", "", ko))
    text = f"{name} {ko}"
    if re.search(r"(?:^|[_\s])(?:id|code|cd|key)(?:$|[_\s])|(?:코드|아이디|식별자)$", name, re.I):
        return Semantic("category")
    if re.search(r"율|비중|점유비|(?:지수|계수|점수)(?:\s*[（(\[].*)?$", text.strip()):
        return Semantic("measure", "%" if "%" in text else "", False, "비율이나 지표는 합계로 계산하지 않아요")
    if re.fullmatch(r"(?:기준\s*)?(?:연도|년도)", name):
        return Semantic("time")
    if re.fullmatch(r"(?:(?:기준|등록|거래|집계|발생|접수|관측|기록|측정|작성)(?:일|일자|날짜|일시)|년월일)", re.sub(r"\s+", "", name)) or re.fullmatch(r"(?:(?:기준|등록|거래|집계|발생|접수|관측|기록|측정|작성)(?:일|일자|날짜|일시)|년월일)", re.sub(r"\s+", "", ko)):
        return Semantic("time")
    explicit = re.search(r"(백만\s*원|천\s*원|만\s*원|억\s*원|원|건|개|명|%)\s*[)）\]]?(?=\s|$)", text)
    unit = re.sub(r"\s+", "", explicit.group(1)) if explicit else sem.unit
    if unit == "%":
        return Semantic("measure", unit, False, "비율은 월별로 더할 수 없어요")
    if sem.role == "unknown" and re.search(r"판매액|판매량|수량|총액|합계", text):
        return Semantic("measure", unit, True)
    return Semantic(sem.role, unit, sem.additive, sem.note)
