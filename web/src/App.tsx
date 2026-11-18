import { useState } from "react"
import { WifiOff } from "lucide-react"
import { STATIC, type Analysis, type AnalyzeOptions, type Dataset } from "@/lib/api"
import { Pill } from "@/components/kit"
import { Toaster } from "@/components/ui/sonner"
import { CarePanel } from "@/components/CarePanel"
import { cn } from "@/lib/utils"
import { Upload } from "@/steps/Upload"
import { Understand } from "@/steps/Understand"
import { Analyze } from "@/steps/Analyze"
import { Result } from "@/steps/Result"
import symbol from "@/assets/symbol.png"

const STEPS = ["넣기", "이해", "분석", "결과"] as const

export default function App() {
  const [step, setStep] = useState(0)
  const [dataset, setDataset] = useState<Dataset | null>(null)
  const [choice, setChoice] = useState<AnalyzeOptions>({})
  const [analysis, setAnalysis] = useState<Analysis | null>(null)

  const go = (n: number) => {
    setStep(n)
    window.scrollTo({ top: 0, behavior: "smooth" })
  }

  return (
    <div className="min-h-dvh">
      <header className="no-print sticky top-0 z-20 border-b border-[var(--grey-200)] bg-background/85 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-3xl items-center gap-3 px-4 sm:px-6">
          <img src={symbol} alt="" className="size-8" />
          <span className="whitespace-nowrap text-[17px] font-bold tracking-[-0.01em]">한 장 제주</span>
          <span className="ml-auto flex items-center gap-2">
            <Pill tone="grey">
              {STATIC ? "공개 체험판" : <><WifiOff className="size-3.5" /><span className="sr-only sm:not-sr-only whitespace-nowrap">인터넷 없이 동작</span></>}
            </Pill>
            {!STATIC && (
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
              className={cn(
                "flex-1 rounded-full py-1.5 text-[14px] font-semibold transition-colors",
                i === step ? "bg-primary text-primary-foreground" : i < step ? "bg-secondary text-secondary-foreground" : "bg-[var(--grey-200)] text-[var(--grey-500)]",
              )}
            >
              {i + 1}. {s}
            </button>
          ))}
        </nav>
      </header>

      <main className="mx-auto max-w-3xl px-4 pt-8 pb-4 sm:px-6">
        {step === 0 && (
          <Upload
            onPick={(ds) => {
              setDataset(ds)
              setChoice({})
              go(1)
            }}
          />
        )}
        {step === 1 && dataset && <Understand dataset={dataset} onBack={() => go(0)} onNext={() => go(2)} />}
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
