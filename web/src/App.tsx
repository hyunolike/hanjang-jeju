import { useEffect, useRef, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { clearUpload } from "@/lib/upload"
import { Check, WifiOff } from "lucide-react"
import { STATIC, WEB_UPLOAD, type Analysis, type AnalyzeOptions, type Dataset } from "@/lib/api"
import { Pill } from "@/components/kit"
import { Toaster } from "@/components/ui/sonner"
import { CarePanel } from "@/components/CarePanel"
import { cn } from "@/lib/utils"
import { Upload } from "@/steps/Upload"
import { Understand } from "@/steps/Understand"
import { Analyze } from "@/steps/Analyze"
import { Result } from "@/steps/Result"
import symbol from "@/assets/brand/logo-v2.webp"

const STEPS = ["자료 넣기", "기준 확인", "발견 보기", "한 장 완성"] as const

export default function App() {
  const queryClient = useQueryClient()
  const [step, setStep] = useState(0)
  const [dataset, setDataset] = useState<Dataset | null>(null)
  const [choice, setChoice] = useState<AnalyzeOptions>({})
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [direction, setDirection] = useState<"forward" | "back">("forward")
  const mainRef = useRef<HTMLElement>(null)
  const lastFocusedStep = useRef(step)

  useEffect(() => {
    if (lastFocusedStep.current === step) return
    lastFocusedStep.current = step
    mainRef.current?.focus({ preventScroll: true })
  }, [step])

  const go = (n: number) => {
    if (n === 0 && WEB_UPLOAD) {
      clearUpload()
      void queryClient.cancelQueries({ predicate: q => q.queryKey.some(key => typeof key === "string" && key.startsWith("web-")) })
      queryClient.removeQueries({ predicate: q => q.queryKey.some(key => typeof key === "string" && key.startsWith("web-")) })
      setDataset(null)
      setAnalysis(null)
      setChoice({})
    }
    setDirection(n < step ? "back" : "forward")
    setStep(n)
    window.scrollTo({ top: 0, behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" })
  }

  return (
    <div className="min-h-dvh">
      <header className="no-print sticky top-0 z-20 border-b border-[var(--grey-200)] bg-background/85 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-3xl items-center gap-3 px-4 sm:px-6">
          <img src={symbol} alt="" width={36} height={36} className="size-9" />
          <span className="whitespace-nowrap text-[17px] font-bold tracking-[-0.01em]">한 장 제주</span>
          <span className="ml-auto flex items-center gap-2">
            <Pill tone="grey">
              {STATIC || WEB_UPLOAD ? "공개 체험판" : <><WifiOff className="size-3.5" /><span className="sr-only sm:not-sr-only whitespace-nowrap">인터넷 없이 동작</span></>}
            </Pill>
            {!STATIC && !WEB_UPLOAD && (
              <CarePanel
                onCleared={() => {
                  setDataset(null)
                  setAnalysis(null)
                  go(0)
                }}
              />
            )}
          </span>
        </div>
        <nav aria-label="단계" className="mx-auto flex max-w-3xl gap-1.5 px-4 pb-3 sm:px-6">
          {STEPS.map((s, i) => (
            <button
              key={s}
              disabled={i > step}
              onClick={() => go(i)}
              aria-current={i === step ? "step" : undefined}
              aria-label={`${i + 1}단계 ${s}${i < step ? ", 완료" : ""}`}
              className={cn("journey-step", i === step && "journey-step-current", i < step && "journey-step-complete")}
            >
              <span className="journey-marker" aria-hidden="true">{i < step ? <Check className="size-3.5" /> : i + 1}</span><span>{s}</span>
            </button>
          ))}
        </nav>
      </header>

      <main key={step} ref={mainRef} tabIndex={-1} aria-label={`${step + 1}단계 ${STEPS[step]}`} data-direction={direction} className="stage-page mx-auto max-w-3xl px-4 pt-7 pb-4 outline-none sm:px-6">
        {step === 0 && (
          <Upload
            onPick={(ds) => {
              setDataset(ds)
              setChoice({})
              go(1)
            }}
          />
        )}
        {step === 1 && dataset && <Understand key={dataset.id} dataset={dataset} onBack={() => go(0)} onNext={() => { setChoice({}); setAnalysis(null); go(2) }} />}
        {step === 2 && dataset && (
          <Analyze
            dataset={dataset}
            choice={choice}
            onChange={setChoice}
            onBack={() => go(1)}
            onNext={(a) => {
              setAnalysis(a)
              go(3)
            }}
          />
        )}
        {step === 3 && analysis && (
          <Result
            analysis={analysis}
            onBack={() => go(2)}
            onDone={() => {
              setDataset(null)
              setAnalysis(null)
              go(0)
            }}
          />
        )}
      </main>
      <Toaster position="top-center" />
    </div>
  )
}
