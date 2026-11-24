import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { CheckCircle2, CircleAlert, ShieldCheck, Trash2 } from "lucide-react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { cn } from "@/lib/utils"

/** 머리글의 "점검과 지우기": 자가 점검, 끝낼 때 자동 지우기(ON/OFF), 지금 지우기. */
export function CarePanel({ onCleared }: { onCleared: () => void }) {
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [confirm, setConfirm] = useState(false)
  const check = useQuery({ queryKey: ["selfcheck"], queryFn: api.selfcheck, refetchInterval: open ? 3000 : 15000 })
  const auto = useMutation({ mutationFn: api.setAutoDelete, onSuccess: () => qc.invalidateQueries({ queryKey: ["selfcheck"] }) })
  const clear = useMutation({
    mutationFn: api.clearWorkspace,
    onSuccess: async (r) => {
      toast.success(r.removed ? `내 자료 ${r.removed}개를 지웠어요` : "지울 자료가 없어요")
      setConfirm(false)
      const related = (q: { queryKey: readonly unknown[] }) => ['datasets', 'understand', 'analyze', 'quality', 'comparison'].includes(String(q.queryKey[0]))
      await qc.cancelQueries({ predicate: related })
      qc.removeQueries({ predicate: related })
      qc.invalidateQueries()
      onCleared()
    },
  })

  // 지난번 비정상 종료로 남은 작업을 시작할 때 지웠다면 한 번 알려 준다.
  const cleared = check.data?.startup_cleared ?? 0
  useEffect(() => {
    if (cleared) toast.message(`지난번에 남은 자료 ${cleared}개를 시작하면서 지웠어요`, { id: "startup-cleared" })
  }, [cleared])

  const items = (check.data?.items ?? []).filter((i) => i.key !== "auto_delete")
  const problems = items.filter((i) => !i.ok && !i.optional).length
  const autoOn = check.data?.auto_delete ?? true

  return (
    <Dialog open={open} onOpenChange={(o) => { setOpen(o); setConfirm(false) }}>
      <DialogTrigger
        render={
          <button
            className={cn(
              "inline-flex h-8 items-center gap-1.5 whitespace-nowrap rounded-full px-3 text-[13px] font-semibold",
              problems ? "bg-[var(--caution-50)] text-[var(--caution)]" : "bg-secondary text-secondary-foreground",
            )}
          />
        }
      >
        <ShieldCheck className="size-4" /> 점검과 지우기
      </DialogTrigger>
      <DialogContent className="max-w-md rounded-[22px] p-6">
        <DialogHeader>
          <DialogTitle className="text-[20px] font-bold">점검과 지우기</DialogTitle>
          <DialogDescription className="text-[14px]">이 PC 안에서만 동작하는지, 내 자료가 남지 않는지 확인해요.</DialogDescription>
        </DialogHeader>

        <ul className="mt-2 divide-y divide-[var(--grey-200)]">
          {items.map((i) => (
            <li key={i.key} className="flex items-start gap-3 py-2.5">
              {i.ok ? (
                <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-primary" />
              ) : (
                <CircleAlert className={cn("mt-0.5 size-5 shrink-0", i.optional ? "text-[var(--grey-500)]" : "text-[var(--caution)]")} />
              )}
              <div className="min-w-0">
                <p className="text-[15px] font-semibold">{i.label}{i.optional && !i.ok && <span className="ml-1 text-[13px] font-normal text-muted-foreground">(없어도 직접 골라 분석할 수 있어요)</span>}</p>
                <p className="break-words text-[14px] text-muted-foreground">{i.detail}</p>
              </div>
            </li>
          ))}
        </ul>

        <div className="mt-3 flex items-center justify-between rounded-2xl bg-[var(--grey-100)] p-4">
          <div>
            <p className="text-[15px] font-semibold">끝낼 때 자동으로 지우기</p>
            <p className="text-[13px] text-muted-foreground">창을 닫으면 넣은 자료를 지워요</p>
          </div>
          <button
            role="switch"
            aria-checked={autoOn}
            aria-label="끝낼 때 자동으로 지우기"
            onClick={() => auto.mutate(!autoOn)}
            className={cn("relative h-7 w-12 rounded-full transition-colors", autoOn ? "bg-primary" : "bg-[var(--grey-300)]")}
          >
            <span className={cn("absolute top-0.5 size-6 rounded-full bg-white shadow transition-[left]", autoOn ? "left-[22px]" : "left-0.5")} />
          </button>
        </div>

        {confirm ? (
          <div className="mt-3 rounded-2xl border border-[var(--caution)] p-4">
            <p className="text-[15px]">넣은 자료를 모두 지울까요? 되돌릴 수 없어요.</p>
            <div className="mt-3 flex gap-2">
              <Button variant="soft" size="md" className="flex-1" onClick={() => setConfirm(false)}>
                그만두기
              </Button>
              <Button size="md" className="flex-1" onClick={() => clear.mutate()} disabled={clear.isPending}>
                <Trash2 /> 지우기
              </Button>
            </div>
          </div>
        ) : (
          <Button variant="soft" size="md" className="mt-3 w-full" onClick={() => setConfirm(true)}>
            <Trash2 /> 지금 내 작업 지우기
          </Button>
        )}
        {check.data?.workspace && <p className="mt-2 break-all text-[12px] text-muted-foreground">작업 폴더: {check.data.workspace}</p>}
      </DialogContent>
    </Dialog>
  )
}
