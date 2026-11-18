/** 숫자를 읽기 쉬운 한국어 단위로. 원 단위는 억, 만으로 줄이고 단위를 숫자 옆에 붙인다. */
export function money(value: number, unit: string): string {
  if (unit === "백만 원") return money(value * 1_000_000, "원")
  if (unit === "원") {
    const abs = Math.abs(value)
    if (abs >= 1e8) return `${trim(value / 1e8)}억 원`
    if (abs >= 1e4) return `${trim(value / 1e4)}만 원`
    return `${Math.round(value).toLocaleString("ko-KR")}원`
  }
  return number(value, unit)
}

export function number(value: number, unit = ""): string {
  if (unit === "배") return `${Number(value.toFixed(2)).toLocaleString("ko-KR")}배`
  const abs = Math.abs(value)
  const text = abs >= 1e8 ? `${trim(value / 1e8)}억` : abs >= 1e4 ? `${trim(value / 1e4)}만` : trim(value)
  return unit ? `${text}${unit === "%" || unit === "%p" || unit === "배" || unit === "월" ? "" : " "}${unit}` : text
}

function trim(value: number): string {
  const digits = Math.abs(value) >= 100 ? 0 : 1
  return Number(value.toFixed(digits)).toLocaleString("ko-KR")
}

export function factText(value: number, unit: string): string {
  return unit === "원" || unit === "백만 원" ? money(value, unit) : number(value, unit)
}

export function period(p: string): string {
  const [y, m] = p.split("-")
  return m ? `${y}년 ${Number(m)}월` : p
}
