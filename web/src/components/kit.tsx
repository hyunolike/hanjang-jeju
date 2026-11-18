import type { ReactNode } from "react"
import { ChevronRight, type LucideIcon } from "lucide-react"
import { cn } from "@/lib/utils"

/** 3D 아이콘. Codex로 만든 그림이 없으면 선 아이콘으로 대신한다. */
const ICONS = import.meta.glob("@/assets/3d/*.png", { eager: true, import: "default" }) as Record<string, string>

export function Illust({ name, fallback: Fallback, className }: { name: string; fallback: LucideIcon; className?: string }) {
  const src = Object.entries(ICONS).find(([path]) => path.endsWith(`/${name}.png`))?.[1]
  if (src) return <img src={src} alt="" aria-hidden className={cn("size-12 object-contain", className)} />
  return (
    <span className={cn("grid size-12 place-items-center rounded-2xl bg-secondary text-primary", className)} aria-hidden>
      <Fallback className="size-6" />
    </span>
  )
}

/** 화면마다 하나의 큰 질문이나 결론. 토스처럼 문장으로 말한다. */
export function BigTitle({ eyebrow, title, sub }: { eyebrow?: string; title: ReactNode; sub?: ReactNode }) {
  return (
    <header className="space-y-2">
      {eyebrow && <p className="text-[15px] font-semibold text-primary">{eyebrow}</p>}
      <h1 className="text-[26px] leading-[1.35] font-bold tracking-[-0.02em] text-foreground sm:text-[30px]">{title}</h1>
      {sub && <p className="text-[17px] leading-relaxed text-[var(--grey-700)]">{sub}</p>}
    </header>
  )
}

export function Panel({ title, action, children, className }: { title?: ReactNode; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cn("rounded-[22px] bg-card p-6 shadow-[0_1px_2px_rgba(0,0,0,0.03)]", className)}>
      {(title || action) && (
        <div className="mb-4 flex items-center justify-between gap-3">
          {title && <h2 className="text-[19px] font-bold tracking-[-0.01em]">{title}</h2>}
          {action}
        </div>
      )}
      {children}
    </section>
  )
}

/** 토스 목록 한 줄: 아이콘, 제목과 설명, 오른쪽 값이나 화살표. */
export function ListRow({
  icon,
  title,
  sub,
  right,
  onClick,
  chevron = !!onClick,
}: {
  icon?: ReactNode
  title: ReactNode
  sub?: ReactNode
  right?: ReactNode
  onClick?: () => void
  chevron?: boolean
}) {
  const Comp = onClick ? "button" : "div"
  return (
    <Comp
      onClick={onClick}
      className={cn(
        "flex w-full items-center gap-4 rounded-2xl px-3 py-3.5 text-left",
        onClick && "transition-colors hover:bg-[var(--grey-50)] active:scale-[0.99] active:bg-[var(--grey-100)]",
      )}
    >
      {icon}
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[17px] font-semibold text-foreground">{title}</span>
        {sub && <span className="mt-0.5 block truncate text-[14px] text-muted-foreground">{sub}</span>}
      </span>
      {right && <span className="shrink-0 text-[15px] text-[var(--grey-700)]">{right}</span>}
      {chevron && <ChevronRight className="size-5 shrink-0 text-[var(--grey-400)]" />}
    </Comp>
  )
}

type Tone = "teal" | "grey" | "positive" | "caution" | "violet" | "danger"
const TONES: Record<Tone, string> = {
  teal: "bg-secondary text-secondary-foreground",
  grey: "bg-[var(--grey-100)] text-[var(--grey-700)]",
  positive: "bg-[var(--positive-50)] text-[var(--positive)]",
  caution: "bg-[var(--caution-50)] text-[var(--caution)]",
  violet: "bg-[var(--violet-50)] text-[var(--violet)]",
  danger: "bg-[#fdeceb] text-[#c2332b]",
}

export function Pill({ tone = "grey", children }: { tone?: Tone; children: ReactNode }) {
  return <span className={cn("inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[13px] font-semibold", TONES[tone])}>{children}</span>
}

/** 큰 숫자 하나와 설명. */
export function Stat({ label, value, tone }: { label: string; value: ReactNode; tone?: "violet" }) {
  return (
    <div>
      <p className="text-[14px] text-muted-foreground">{label}</p>
      <p className={cn("num mt-1 text-[24px] font-bold tracking-[-0.02em]", tone === "violet" && "text-[var(--violet)]")}>{value}</p>
    </div>
  )
}

/** 화면 아래에 붙는 큰 행동 버튼 영역. */
export function CtaBar({ children }: { children: ReactNode }) {
  return (
    <div className="no-print sticky bottom-0 z-10 -mx-4 mt-8 bg-gradient-to-t from-background via-background/95 to-transparent px-4 pt-6 pb-6 sm:-mx-6 sm:px-6">
      <div className="flex gap-3">{children}</div>
    </div>
  )
}
