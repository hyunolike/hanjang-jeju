import type { ReactNode } from "react"
import { AlertCircle, CheckCircle2, Info } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

type ControlProps = { id: string; "aria-describedby": string; "aria-invalid": boolean }

export function FormField({ id, label, optional, description, error, children }: { id: string; label: string; optional?: boolean; description: ReactNode; error?: string; children: (props: ControlProps) => ReactNode }) {
  return <div className="form-field">
    <label htmlFor={id} className="form-field-label">{label}{optional && <span className="ml-2 text-[14px] font-normal text-muted-foreground">선택</span>}</label>
    {children({ id, "aria-describedby": `${id}-message`, "aria-invalid": !!error })}
    <div id={`${id}-message`} className={cn("form-field-message", error && "text-destructive")} role={error ? "alert" : undefined}>{error ? <span className="flex items-start gap-2"><AlertCircle aria-hidden className="mt-0.5 size-4 shrink-0" />{error}</span> : description}</div>
  </div>
}

export function ActionFeedback({ tone = "info", title, description, action }: { tone?: "info" | "caution" | "positive" | "danger"; title: string; description?: ReactNode; action?: { label: string; onClick: () => void } }) {
  const Icon = tone === "positive" ? CheckCircle2 : tone === "danger" || tone === "caution" ? AlertCircle : Info
  return <div className={cn("form-feedback", `form-feedback-${tone}`)}>
    <div className="flex items-start gap-3" role={tone === "danger" ? "alert" : "status"}>
      <Icon aria-hidden className="mt-0.5 size-5 shrink-0" />
      <div className="min-w-0"><p className="text-[16px] font-semibold leading-relaxed">{title}</p>{description && <div className="mt-1 text-[15px] leading-relaxed">{description}</div>}</div>
    </div>
    {action && <Button type="button" variant="outline" size="md" className="mt-3 max-w-full whitespace-normal" onClick={action.onClick}>{action.label}</Button>}
  </div>
}
