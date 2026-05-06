'use client'

import { SessionStats } from '../types'

interface StatsPanelProps {
  stats: SessionStats | null
  isVisible: boolean
  isStreaming: boolean
}

export default function StatsPanel({ stats, isVisible, isStreaming }: StatsPanelProps) {
  return (
    <aside className="stats-panel">
      {/* Live status card */}
      <div className="stat-card">
        <div className="stat-card-title">
          <span style={{
            width: 6, height: 6, borderRadius: '50%',
            background: isStreaming ? 'var(--success)' : 'var(--text-3)',
            display: 'inline-block',
            boxShadow: isStreaming ? '0 0 6px var(--success)' : 'none',
            animation: isStreaming ? 'pulse-dot 1s ease infinite' : 'none',
          }} />
          Firewall Status
        </div>
        <div className="stat-row">
          <span className="stat-label">State</span>
          <span className={`stat-value ${isStreaming ? 'green' : 'blue'}`}>
            {isStreaming ? 'ACTIVE' : 'READY'}
          </span>
        </div>
        <div className="stat-row">
          <span className="stat-label">Provider</span>
          <span className="stat-value purple">Gemini</span>
        </div>
        <div className="stat-row">
          <span className="stat-label">Detection</span>
          <span className="stat-value blue">Entropy</span>
        </div>
      </div>

      {/* Live metrics */}
      {isVisible && stats && (
        <div className="stat-card animate-in">
          <div className="stat-card-title">
            📊 Pipeline Metrics
          </div>
          <div className="stat-row">
            <span className="stat-label">Claims found</span>
            <span className="stat-value yellow">{stats.total_claims_detected}</span>
          </div>
          <div className="stat-row">
            <span className="stat-label">Verified</span>
            <span className="stat-value green">{stats.claims_verified}</span>
          </div>
          <div className="stat-row">
            <span className="stat-label">Hallucinations</span>
            <span className={`stat-value ${stats.hallucinations_found > 0 ? 'red' : 'green'}`}>
              {stats.hallucinations_found}
            </span>
          </div>
          <div className="stat-row">
            <span className="stat-label">Corrections</span>
            <span className={`stat-value ${stats.corrections_made > 0 ? 'red' : 'green'}`}>
              {stats.corrections_made}
            </span>
          </div>
          <div className="stat-row">
            <span className="stat-label">Skipped</span>
            <span className="stat-value blue">{stats.claims_skipped}</span>
          </div>
        </div>
      )}

      {/* Latency */}
      {isVisible && stats && (
        <div className="stat-card animate-in">
          <div className="stat-card-title">⚡ Latency</div>
          <div className="stat-row">
            <span className="stat-label">Avg verify</span>
            <span className="stat-value green">
              {stats.avg_verification_latency_ms.toFixed(1)}ms
            </span>
          </div>
          {stats.total_pipeline_latency_ms > 0 && (
            <div className="stat-row">
              <span className="stat-label">Pipeline total</span>
              <span className="stat-value blue">
                {stats.total_pipeline_latency_ms.toFixed(0)}ms
              </span>
            </div>
          )}
          <div className="stat-row">
            <span className="stat-label">Target</span>
            <span className="stat-value purple">&lt;200ms</span>
          </div>
        </div>
      )}

      {/* Info card */}
      <div className="stat-card">
        <div className="stat-card-title">ℹ️ How It Works</div>
        <div style={{ fontSize: '0.72rem', color: 'var(--text-3)', lineHeight: 1.6 }}>
          <p style={{ marginBottom: 6 }}>
            Per-token Shannon entropy from Gemini logprobs flags uncertain spans.
          </p>
          <p style={{ marginBottom: 6 }}>
            NLI classifier verifies flagged claims against the ground truth vault.
          </p>
          <p>
            Contradictions trigger the REVERSE rewriter before reaching your screen.
          </p>
        </div>
      </div>
    </aside>
  )
}
