'use client'

import { EvalComplete, ModelEvalResult } from '../types'

const DIM_LABELS: Record<string, string> = {
  factuality:            'Factuality',
  hallucination_rate:    'Hallucination Safety',
  reasoning:             'Reasoning Quality',
  instruction_following: 'Instruction Follow',
}

const DIM_COLORS: Record<string, string> = {
  factuality:            '#6366f1',
  hallucination_rate:    '#10b981',
  reasoning:             '#f59e0b',
  instruction_following: '#60a5fa',
}

function scoreToGrade(score: number): string {
  if (score >= 0.85) return 'A'
  if (score >= 0.70) return 'B'
  if (score >= 0.55) return 'C'
  if (score >= 0.40) return 'D'
  return 'F'
}

function ScoreRing({ score, size = 56 }: { score: number; size?: number }) {
  const r   = (size - 8) / 2
  const circ = 2 * Math.PI * r
  const fill = circ * score
  const grade = scoreToGrade(score)

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <circle cx={size/2} cy={size/2} r={r}
        fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth={4} />
      <circle cx={size/2} cy={size/2} r={r}
        fill="none" stroke="#6366f1" strokeWidth={4}
        strokeDasharray={`${fill} ${circ}`}
        strokeLinecap="round"
        transform={`rotate(-90 ${size/2} ${size/2})`}
        style={{ transition: 'stroke-dasharray 0.8s ease' }}
      />
      <text x="50%" y="50%" dominantBaseline="middle" textAnchor="middle"
        fill="#f1f5f9" fontSize={size > 48 ? 11 : 9} fontWeight="700"
        fontFamily="monospace">
        {grade}
      </text>
    </svg>
  )
}

function ModelCard({
  result, isWinner, dimWinners, otherScore
}: {
  result: ModelEvalResult
  isWinner: boolean
  dimWinners: Record<string, string>
  otherScore: number
}) {
  const margin = ((result.overall_score - otherScore) * 100).toFixed(1)
  const ahead  = result.overall_score > otherScore

  return (
    <div className={`model-card${isWinner ? ' winner' : ''}`}>
      <div className="model-card-header">
        <div>
          <div className="model-card-name">{result.model_label}</div>
          <div style={{ fontSize: '0.68rem', color: 'var(--text-3)', marginTop: 2 }}>
            {result.tokens_total} tokens · {result.latency_ms.toFixed(0)}ms
          </div>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          {isWinner && <span className="model-card-badge badge-winner">🏆 Winner</span>}
          <span className="model-card-badge badge-score">
            {(result.overall_score * 100).toFixed(1)}%
          </span>
        </div>
      </div>

      <div className="model-card-body">
        {/* Score ring + margin */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 14 }}>
          <ScoreRing score={result.overall_score} size={60} />
          <div>
            <div style={{ fontSize: '1.4rem', fontWeight: 800, color: 'var(--text-1)',
              fontFamily: 'var(--font-mono)' }}>
              {(result.overall_score * 100).toFixed(1)}
              <span style={{ fontSize: '0.75rem', color: 'var(--text-3)', fontWeight: 400 }}>%</span>
            </div>
            {ahead ? (
              <div style={{ fontSize: '0.72rem', color: 'var(--success)' }}>
                +{margin}% ahead
              </div>
            ) : (
              <div style={{ fontSize: '0.72rem', color: 'var(--text-3)' }}>
                {Math.abs(Number(margin))}% behind
              </div>
            )}
          </div>
          <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
            <div style={{ fontSize: '0.68rem', color: 'var(--text-3)' }}>Hallucination</div>
            <div style={{ fontSize: '0.85rem', fontWeight: 700, fontFamily: 'var(--font-mono)',
              color: result.hallucination_rate < 0.1 ? 'var(--success)' : 'var(--warning)' }}>
              {(result.hallucination_rate * 100).toFixed(1)}%
            </div>
            <div style={{ fontSize: '0.68rem', color: 'var(--text-3)', marginTop: 4 }}>Corrections</div>
            <div style={{ fontSize: '0.85rem', fontWeight: 700, fontFamily: 'var(--font-mono)',
              color: result.corrections === 0 ? 'var(--success)' : 'var(--danger)' }}>
              {result.corrections}
            </div>
          </div>
        </div>

        {/* Dimension bars */}
        <div className="dim-bars">
          {Object.entries(DIM_LABELS).map(([key, label]) => {
            const dim     = result.dimensions[key]
            const score   = dim?.score ?? 0
            const won     = dimWinners[key] === result.model_id
            return (
              <div key={key} className="dim-row">
                <div className="dim-name">
                  {won && <span style={{ color: 'var(--accent)', marginRight: 4 }}>▸</span>}
                  {label}
                </div>
                <div className="dim-bar-track">
                  <div
                    className="dim-bar-fill"
                    style={{
                      width:      `${score * 100}%`,
                      background: DIM_COLORS[key] || 'var(--accent)',
                      opacity:    won ? 1 : 0.55,
                    }}
                  />
                </div>
                <div className="dim-score">{(score * 100).toFixed(0)}%</div>
              </div>
            )
          })}
        </div>

        {/* Response preview */}
        <div style={{ fontSize: '0.68rem', color: 'var(--text-3)',
          textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>
          Response Preview
        </div>
        <div className="response-preview">
          {result.response.slice(0, 300)}{result.response.length > 300 ? '…' : ''}
        </div>
      </div>
    </div>
  )
}

interface EvalViewProps {
  evalResult: EvalComplete | null
  isLoading: boolean
  loadingStatus: string
}

export default function EvalView({ evalResult, isLoading, loadingStatus }: EvalViewProps) {
  if (isLoading) {
    return (
      <div className="eval-loading">
        <div style={{ fontSize: '1.5rem' }}>⚙️</div>
        <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-2)' }}>
          {loadingStatus || 'Running evaluation...'}
        </div>
        <div className="eval-loading-bar">
          <div className="eval-loading-fill" />
        </div>
        <div style={{ fontSize: '0.72rem' }}>
          Running both models in parallel · Scoring dimensions · LLM-as-judge comparison
        </div>
      </div>
    )
  }

  if (!evalResult) {
    return (
      <div className="eval-loading">
        <div className="stream-placeholder-icon" style={{ fontSize: '1.4rem' }}>⚖️</div>
        <div className="stream-placeholder-title">Evaluation Mode</div>
        <div className="stream-placeholder-sub">
          Submit a query to run Gemini 1.5 Flash vs Gemini 2.0 Flash Lite
          through the multi-dimensional evaluation framework.
          Results include factuality, hallucination rate, reasoning, and
          instruction-following scores with LLM-as-judge comparison.
        </div>
      </div>
    )
  }

  const [modelA, modelB] = evalResult.models
  if (!modelA || !modelB) return null

  return (
    <>
      {/* Verdict */}
      <div className="verdict-card animate-in">
        <div className="verdict-icon">🏆</div>
        <div style={{ flex: 1 }}>
          <div className="verdict-winner">{evalResult.winner_label} Wins</div>
          <div className="verdict-text">{evalResult.verdict}</div>
          <div className="verdict-rationale">{evalResult.rationale}</div>
          <div className="dim-winners">
            {Object.entries(evalResult.dimension_winner).map(([dim, winner_id]) => {
              const winner = evalResult.models.find(m => m.model_id === winner_id)
              return (
                <span key={dim} className="dim-winner-chip">
                  {DIM_LABELS[dim] || dim}: <span>{winner?.model_label || winner_id}</span>
                </span>
              )
            })}
          </div>
        </div>
      </div>

      {/* Model cards */}
      <ModelCard
        result={modelA}
        isWinner={evalResult.winner === modelA.model_id}
        dimWinners={evalResult.dimension_winner}
        otherScore={modelB.overall_score}
      />
      <ModelCard
        result={modelB}
        isWinner={evalResult.winner === modelB.model_id}
        dimWinners={evalResult.dimension_winner}
        otherScore={modelA.overall_score}
      />
    </>
  )
}
