import { useRef, useState } from "react"
import { useMutation, useQuery } from "@tanstack/react-query"
import { Database, Download, FileSpreadsheet, FlaskConical, Upload as UploadIcon } from "lucide-react"
import { toast } from "sonner"
import { api, STATIC, WEB_UPLOAD, type Dataset } from "@/lib/api"
import { useQueryClient } from "@tanstack/react-query"
import { Illust, ListRow, Panel, Pill } from "@/components/kit"
import { StageIntro } from "@/components/stage"
import { buttonVariants } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"

export function Upload({ onPick }: { onPick: (ds: Dataset) => void }) {
  const queryClient = useQueryClient()
  const list = useQuery({ queryKey: ["datasets"], queryFn: api.datasets })
  const input = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)
  const upload = useMutation({
    mutationFn: api.upload,
    onSuccess: (ds) => {
      if (WEB_UPLOAD) queryClient.removeQueries({ predicate: (q) => q.queryKey.some((key) => typeof key === "string" && key.startsWith("web-")) })
      toast.success("자료를 넣었어요")
      onPick(ds)
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const groups: { key: Dataset["source"]; title: string; sub: string; icon: typeof Database }[] = [
    { key: "upload", title: "내가 넣은 자료", sub: "이 PC에만 있어요", icon: FileSpreadsheet },
    { key: "hub", title: "제주데이터허브 공개 자료", sub: "실제 값이에요. 바로 체험해 볼 수 있어요", icon: Database },
    { key: "dummy", title: "센터 자료 예시", sub: "공개 명세서로 만든 더미 값이에요", icon: FlaskConical },
  ]

  return (
    <div className="space-y-6">
      <StageIntro stage="upload" title={<>제주 데이터,<br />한 장으로 읽어요</>} description={STATIC && !WEB_UPLOAD ? "아래 공개 예시로 흐름을 살펴보세요. 내 CSV는 PC용 프로그램에서 분석할 수 있어요." : WEB_UPLOAD ? "공개 가능한 CSV를 넣어 주세요. 날짜와 숫자를 정리해 흐름을 찾아드릴게요." : "센터에서 내려받은 CSV로 시작해 보세요. 날짜와 숫자를 정리해 흐름을 찾아드릴게요."} />

      {STATIC && !WEB_UPLOAD ? (
        <Panel>
          <div className="flex items-center gap-5">
            <Illust name="offline" fallback={UploadIcon} className="size-16" />
            <div>
              <p className="text-[19px] font-bold">공개 체험판이에요</p>
              <p className="mt-1 text-[15px] leading-relaxed text-muted-foreground">
                아래 공개 자료로 모든 기능을 볼 수 있어요. 센터에서 받은 CSV는 밖으로 나가면 안 되니, 센터 PC에 설치하는 프로그램에서 넣어 주세요.
              </p>
              <a
                href="https://github.com/hyunolike/hanjang-jeju/releases/latest"
                target="_blank"
                rel="noreferrer"
                className={cn(buttonVariants({ size: "lg" }), "mt-4 gap-2")}
              >
                <Download className="size-4" />
                PC 프로그램 내려받기 (Windows, Mac)
              </a>
            </div>
          </div>
        </Panel>
      ) : (
      <button
        onClick={() => input.current?.click()}
        onDragOver={(e) => {
          e.preventDefault()
          setOver(true)
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setOver(false)
          const file = e.dataTransfer.files[0]
          if (file) upload.mutate(file)
        }}
        className={cn(
          "flex w-full items-center gap-5 rounded-[22px] border-2 border-dashed bg-card p-6 text-left transition-all",
          over ? "border-primary bg-secondary" : "border-[var(--grey-300)] hover:border-primary/60",
        )}
      >
        <Illust name="upload" fallback={UploadIcon} className="size-16" />
        <span className="flex-1">
          <span className="block text-[19px] font-bold">CSV를 끌어다 놓으세요</span>
          <span className="mt-1 block text-[15px] text-muted-foreground">{WEB_UPLOAD ? "최대 3MiB. 분석 서버로 전송하며 파일을 보관하지 않아요." : "눌러서 고를 수도 있어요. 파일은 이 PC 밖으로 나가지 않아요."}</span>
        </span>
        {upload.isPending && <Pill tone="teal">읽는 중</Pill>}
      </button>
      )}
      {WEB_UPLOAD && <p className="text-[14px] leading-relaxed text-muted-foreground">공개할 수 있는 자료만 넣어 주세요. 센터 원본과 주최 제공 제한 자료는 PC용 프로그램을 이용해 주세요. AI에는 질문과 열 정보만 보내요.</p>}
      <input ref={input} type="file" accept=".csv" hidden onChange={(e) => { const file = e.target.files?.[0]; e.target.value = ""; if (file) upload.mutate(file) }} />

      {list.isLoading && <Skeleton className="h-64 rounded-[22px]" />}
      {list.error && <Panel><p className="text-[15px] text-destructive">{(list.error as Error).message}</p></Panel>}
      {groups.map((g) => {
        const items = list.data?.filter((d) => d.source === g.key) ?? []
        if (!items.length) return null
        return (
          <Panel key={g.key} title={g.title} action={<span className="text-[14px] text-muted-foreground">{g.sub}</span>}>
            <div className="-mx-3">
              {items.map((ds) => (
                <ListRow
                  key={ds.id}
                  icon={<Illust name={g.key === "hub" ? "hub" : g.key === "dummy" ? "understand" : "upload"} fallback={g.icon} className="size-11" />}
                  title={ds.title}
                  sub={ds.provider || ds.period ? <>{ds.provider}<span className="ml-2 text-[var(--grey-400)]">{ds.period}</span></> : "직접 넣은 파일"}
                  right={ds.provider === "제주빅데이터센터" ? <Pill tone="teal">센터 제공</Pill> : undefined}
                  onClick={() => onPick(ds)}
                />
              ))}
            </div>
          </Panel>
        )
      })}
    </div>
  )
}
