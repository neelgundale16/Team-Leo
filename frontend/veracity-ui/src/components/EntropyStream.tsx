'use client'

import { Token } from '../types'
import { useEffect, useRef } from 'react'

interface EntropyStreamProps {
  tokens: Token[]
  isStreaming: boolean
}

// Map entropy value to background color for heatmap
function entropyColor(entropy: number): string {
  if (entropy > 0.33)      return 'rgba(239,68,68,0.7)'     // red   — very uncertain
  if (entropy > 0.30)      return 'rgba(245,158,11,0.6)'    // amber — uncertain
  if (entropy > 0.28)      return 'rgba(251,191,36,0.5)'    // yellow — borderline
  if (entropy > 0.15)      return 'rgba(99,102,241,0.25)'   // indigo — slight
  return                          'rgba(148,163,184,0.08)'  // neutral — confident
}

function entropyToWidth(entropy: number): number {
  return Math.max(4, Math.min(24, entropy * 60))
}

export function EntropyStrip({ tokens }: { tokens: Token[] }) {
  return (
    <div className="entropy-strip" title="Token entropy heatmap — red = model was uncertain">
      {tokens.map((t) => (
        <div
          key={t.id}
          className="entropy-tok"
          style={{
            width:      `${entropyToWidth(t.entropy)}px`,
            background: entropyColor(t.entropy),
          }}
          title={`"${t.text.trim()}" entropy: ${t.entropy.toFixed(3)}`}
        />
      ))}
    </div>
  )
}

export default function EntropyStream({ tokens, isStreaming }: EntropyStreamProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [tokens.length])

  if (tokens.length === 0) {
    return (
      <div className="stream-placeholder">
        <div className="stream-placeholder-icon">⚡</div>
        <p className="stream-placeholder-title">Firewall Standing By</p>
        <p className="stream-placeholder-sub">
          Submit a query. The AI response streams here token-by-token,
          with hallucinations auto-corrected in real time.
        </p>
      </div>
    )
  }

  return (
    <div className="token-stream">
      {tokens.map((token) => {
        if (token.status === 'corrected' && token.correction) {
          return (
            <span key={token.id} className="tok tok-corrected">
              <span className="tok-original">{token.text}</span>
              <span className="tok-new">{token.correction}</span>
              <span className="tok-tooltip">
                ✓ Auto-corrected via {token.source}
              </span>
            </span>
          )
        }

        if (token.status === 'high_entropy') {
          return (
            <span
              key={token.id}
              className="tok tok-high-entropy"
              title={`Uncertain token (H=${token.entropy.toFixed(3)})`}
            >
              {token.text}
            </span>
          )
        }

        return (
          <span key={token.id} className="tok tok-normal">
            {token.text}
          </span>
        )
      })}
      {isStreaming && <span className="stream-cursor" />}
      <div ref={bottomRef} />
    </div>
  )
}
