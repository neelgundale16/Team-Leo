'use client';

import { SessionStats } from '@/types';

interface StatsPanelProps {
  stats: SessionStats | null;
  isVisible: boolean;
  isStreaming: boolean;
}

const PIPELINE_STEPS = [
  { key: 'interceptor', name: 'Interceptor',    desc: 'Claim boundary detection' },
  { key: 'sentinel',    name: 'Sentinel',       desc: 'NLI fact classification' },
  { key: 'vault',       name: 'Vault Search',   desc: 'ChromaDB semantic lookup' },
  { key: 'rewriter',    name: 'Rewriter',       desc: 'REVERSE auto-correction' },
];

export default function StatsPanel({ stats, isVisible, isStreaming }: StatsPanelProps) {
  const haluPct = stats && stats.total_claims_detected > 0
    ? Math.round((stats.hallucinations_found / stats.total_claims_detected) * 100)
    : 0;

  const skipPct = stats && stats.total_claims_detected > 0
    ? Math.round((stats.claims_skipped / stats.total_claims_detected) * 100)
    : 0;

  return (
    <aside className={`stats-panel ${isVisible ? 'stats-visible' : 'stats-hidden'}`}>

      {/* ── Live Metrics ─────────────────────────── */}
      <div className="stats-card">
        <div className="stats-header">
          <span className="live-dot" />
          <span className="stats-title">Live Metrics</span>
        </div>

        {stats ? (
          <>
            <div className="stats-body">
              <div className="stat-row">
                <span className="stat-label">
                  <span className="stat-label-dot dot-neutral" />
                  Claims Detected
                </span>
                <span className="stat-value">{stats.total_claims_detected}</span>
              </div>
              <div className="stat-row">
                <span className="stat-label">
                  <span className="stat-label-dot dot-red" />
                  Corrections Made
                </span>
                <span className="stat-value stat-value-red">{stats.corrections_made}</span>
              </div>
              <div className="stat-row">
                <span className="stat-label">
                  <span className="stat-label-dot dot-green" />
                  Verified Clean
                </span>
                <span className="stat-value stat-value-green">{stats.claims_verified}</span>
              </div>
              <div className="stat-row">
                <span className="stat-label">
                  <span className="stat-label-dot dot-amber" />
                  Skipped ({skipPct}%)
                </span>
                <span className="stat-value stat-value-amber">{stats.claims_skipped}</span>
              </div>
              <div className="stat-row">
                <span className="stat-label">
                  <span className="stat-label-dot dot-neutral" />
                  Avg Verify
                </span>
                <span className="stat-value">{stats.avg_verification_latency_ms.toFixed(0)}ms</span>
              </div>
              <div className="stat-row">
                <span className="stat-label">
                  <span className="stat-label-dot dot-neutral" />
                  Pipeline Total
                </span>
                <span className="stat-value">{stats.total_pipeline_latency_ms.toFixed(0)}ms</span>
              </div>
            </div>

            <div className="halu-section">
              <div className="halu-label-row">
                <span className="halu-label">Hallucination Rate</span>
                <span className="halu-pct">{haluPct}%</span>
              </div>
              <div className="halu-track">
                <div className="halu-fill" style={{ width: `${Math.min(100, haluPct)}%` }} />
              </div>
            </div>
          </>
        ) : (
          <div className="stats-empty">
            <p className="stats-empty-text">
              {isStreaming ? 'Processing…' : 'Stats will appear here after your first query.'}
            </p>
          </div>
        )}
      </div>

      {/* ── Pipeline Steps ───────────────────────── */}
      <div className="pipeline-card">
        <div className="pipeline-header">
          <span className="pipeline-title">Pipeline</span>
        </div>
        <div className="pipeline-steps">
          {PIPELINE_STEPS.map((step) => {
            const active = isStreaming || !!stats;
            return (
              <div key={step.key} className="pipeline-step">
                <div className={`step-dot ${active ? 'step-dot-active' : 'step-dot-idle'}`}>
                  {active ? '✓' : '○'}
                </div>
                <div>
                  <div className="step-name">{step.name}</div>
                  <div className="step-desc">{step.desc}</div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

    </aside>
  );
}