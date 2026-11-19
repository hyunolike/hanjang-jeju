import type { ReactNode } from "react"
import { LoaderCircle } from "lucide-react"
import uploadArt from "@/assets/brand/upload-v2.webp"
import understandArt from "@/assets/brand/understand-v2.webp"
import analyzeArt from "@/assets/brand/analyze-v2.webp"
import reportArt from "@/assets/brand/report-v2.webp"

type Stage = "upload" | "understand" | "analyze" | "report"
const STAGES = {
  upload: { label: "1단계 · 자료 넣기", image: uploadArt },
  understand: { label: "2단계 · 기준 확인", image: understandArt },
  analyze: { label: "3단계 · 발견 보기", image: analyzeArt },
  report: { label: "4단계 · 한 장 완성", image: reportArt },
} satisfies Record<Stage, { label: string; image: string }>

/** 그림은 여정의 맥락을 전달하고, 사실과 숫자는 본문이 담당한다. */
export function StageIntro({ stage, title, description }: { stage: Stage; title: ReactNode; description: ReactNode }) {
  const current = STAGES[stage]
  return (
    <header className={`stage-intro stage-intro--${stage}`}>
      <div className="stage-intro-copy">
        <p className="stage-eyebrow">{current.label}</p>
        <h1>{title}</h1>
        <p className="stage-description">{description}</p>
      </div>
      <img className="stage-art" src={current.image} width={720} height={480} alt="" aria-hidden="true" decoding="async" />
    </header>
  )
}

export function StageLoading({ stage }: { stage: "understand" | "analyze" }) {
  return (
    <div className="space-y-5" role="status" aria-live="polite">
      <StageIntro stage={stage} title={stage === "understand" ? "자료의 구조를 읽고 있어요" : "자료에서 흐름을 찾고 있어요"} description={stage === "understand" ? "날짜와 숫자, 비어 있는 값을 확인해요." : "선택한 기준으로 계산하고 있어요. 결과가 준비되면 바로 보여드릴게요."} />
      <div className="stage-loading"><LoaderCircle className="stage-spinner size-5" aria-hidden="true" /><span>처리 중이에요</span></div>
    </div>
  )
}
