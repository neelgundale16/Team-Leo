'use client';

import { SessionStats } from '@/types';

interface StatsPanelProps {
  stats: SessionStats | null;
  isVisible: boolean;
}

function StatRow({
  label,
  value,
  accent,
  suffix,
}: {
  label: string;
  value: number | string;
  accent?: 'red' | 'green' | 'yellow' | 'default';
  suffix?: string;
}) {
  const accentClass =
    accent === 'red'
      ? 'stat-value-red'
      : accent === 'green'
      ? 'stat-value-green'
      : accent === 'yellow'
      ? 'stat-value-yellow'
      : 'stat-value-default';

  return (
    <div className="stat-row">
      <span className="stat-label">{label}</span>
      <span className={`stat-value ${accentClass}`}>
        {value}
        {suffix && <span className="stat-suffix">{suffix}</span>}
      </span>
    </div>
  );
}

export default function StatsPanel({ stats, isVisible }: StatsPanelProps) {
  const efficiencyPct =
    stats && stats.total_claims_detected > 0
      ? Math.round((stats.claims_skipped / stats.total_claims_detected) * 100)
      : 0;

  return (
    <aside className={`stats-panel ${isVisible ? 'stats-visible' : 'stats-hidden'}`}>
      <div className="stats-header">
        <span className="stats-dot" />
        <span className="stats-title">LIVE MONITOR</span>
      </div>

      <div className="stats-divider" />

      {stats ? (
        <div className="stats-body">
          <StatRow
            label="Claims Detected"
            value={stats.total_claims_detected}
            accent="default"
          />
          <StatRow
            label="Corrections Made"
            value={stats.corrections_made}
            accent="red"
          />
          <StatRow
            label="Verified Clean"
            value={stats.claims_verified}
            accent="green"
          />
          <StatRow
            label="Skipped"
            value={`${stats.claims_skipped} (${efficiencyPct}%)`}
            accent="yellow"
          />
          <StatRow
            label="Avg Verify Time"
            value={stats.avg_verification_latency_ms.toFixed(1)}
            accent="default"
            suffix="ms"
          />
          <StatRow
            label="Pipeline Latency"
            value={stats.total_pipeline_latency_ms.toFixed(1)}
            accent="default"
            suffix="ms"
          />

          <div className="stats-divider" />

          <div className="hallucination-meter">
            <span className="meter-label">Hallucination Rate</span>
            <div className="meter-bar-bg">
              <div
                className="meter-bar-fill"
                style={{
                  width: `${
                    stats.total_claims_detected > 0
                      ? Math.min(
                          100,
                          Math.round(
                            (stats.hallucinations_found /
                              stats.total_claims_detected) *
                              100
                          )
                        )
                      : 0
                  }%`,
                }}
              />
            </div>
            <span className="meter-pct">
              {stats.total_claims_detected > 0
                ? Math.round(
                    (stats.hallucinations_found / stats.total_claims_detected) *
                      100
                  )
                : 0}
              %
            </span>
          </div>
        </div>
      ) : (
        <div className="stats-empty">
          <span className="stats-empty-text">Awaiting first query…</span>
        </div>
      )}
    </aside>
  );
}