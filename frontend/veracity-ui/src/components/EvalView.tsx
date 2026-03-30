'use client';

import { ComparisonResult, ModelEvalResult, EvalDimension } from '@/types';

interface EvalViewProps {
  result: ComparisonResult | null;
  progress: string[];
  isLoading: boolean;
}

const DIMENSION_LABELS: Record<string, string> = {
  factuality: 'Factual Grounding',
  hallucination_rate: 'Hallucination Mitigation',
  reasoning: 'Reasoning Clarity',
  instruction_following: 'Task Adherence',
};

const DIMENSION_COLORS: Record<string, string> = {
  factuality: '#3b82f6',
  hallucination_rate: '#f59e0b',
  reasoning: '#8b5cf6',
  instruction_following: '#10b981',
};

function ScoreRing({ score, size = 100, label }: { score: number; size?: number; label: string }) {
  const radius = (size - 10) / 2;
  const circ = 2 * Math.PI * radius;
  const offset = circ - score * circ;
  const color = score >= 0.8 ? '#22c55e' : score >= 0.6 ? '#eab308' : '#ef4444';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)', filter: `drop-shadow(0 0 8px ${color}33)` }}>
        <circle cx={size / 2} cy={size / 2} r={radius}
          fill="none" stroke="rgba(148,163,184,0.1)" strokeWidth="6" />
        <circle cx={size / 2} cy={size / 2} r={radius}
          fill="none" stroke={color} strokeWidth="6"
          strokeDasharray={circ} strokeDashoffset={offset}
          strokeLinecap="round"
          style={{ transition: 'stroke-dashoffset 1.5s cubic-bezier(0.4, 0, 0.2, 1)' }} />
      </svg>
      <div style={{ position: 'relative', marginTop: -(size - 14), height: size - 14, display: 'flex', alignItems: 'center', justifyContent: 'center', width: size }}>
        <span style={{ fontSize: size > 80 ? 24 : 18, fontWeight: 800, fontFamily: 'monospace', color }}>
          {(score * 100).toFixed(0)}
        </span>
      </div>
      <span style={{ fontSize: 12, fontWeight: 700, color: '#94a3b8', textAlign: 'center', marginTop: 8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</span>
      <style>{`@keyframes score-grow { from { stroke-dashoffset: ${circ}; } to { stroke-dashoffset: ${offset}; } }`}</style>
    </div>
  );
}

function DimensionBar({ dim, winner }: { dim: EvalDimension; winner?: boolean }) {
  const color = DIMENSION_COLORS[dim.name] || '#3b82f6';
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <span style={{ fontSize: 13, fontWeight: 700, color: '#f8fafc', display: 'flex', alignItems: 'center', gap: 6 }}>
          {DIMENSION_LABELS[dim.name] || dim.name}
          {winner && <span style={{ fontSize: 10, background: 'rgba(34,197,94,0.15)', color: '#22c55e', padding: '1px 6px', borderRadius: 4, border: '1px solid rgba(34,197,94,0.3)' }}>BEST</span>}
        </span>
        <span style={{ fontSize: 14, fontFamily: 'monospace', fontWeight: 800, color }}>
          {(dim.score * 100).toFixed(0)}%
        </span>
      </div>
      <div style={{ height: 6, borderRadius: 999, background: 'rgba(30,41,59,0.8)', border: '1px solid rgba(148,163,184,0.1)', overflow: 'hidden' }}>
        <div style={{
          height: '100%', borderRadius: 999,
          width: `${dim.score * 100}%`,
          background: color,
          transition: 'width 1.2s cubic-bezier(0.4, 0, 0.2, 1)',
          boxShadow: `0 0 10px ${color}33`
        }} />
      </div>
      <p style={{ fontSize: 11, color: '#64748b', margin: '4px 0 0', lineHeight: 1.4, fontWeight: 500 }}>
        {dim.rationale}
      </p>
    </div>
  );
}

function ModelCard({ model, isWinner, dimensionWinner }: {
  model: ModelEvalResult;
  isWinner: boolean;
  dimensionWinner: Record<string, string>;
}) {
  const dims = Object.values(model.dimensions || {});
  return (
    <div className="fade-in" style={{
      flex: 1, minWidth: 320, borderRadius: 20, padding: 24,
      border: `2px solid ${isWinner ? 'rgba(34,197,94,0.4)' : 'rgba(148,163,184,0.15)'}`,
      background: isWinner ? 'rgba(34,197,94,0.05)' : 'rgba(15,23,42,0.4)',
      boxShadow: isWinner ? '0 20px 25px -5px rgba(34,197,94,0.1)' : '0 10px 15px -3px rgba(0,0,0,0.1)',
      transition: 'all 0.3s ease-out',
      position: 'relative'
    }}>
      {/* Winner Badge — Floating Top Right */}
      {isWinner && (
        <div style={{
          position: 'absolute', top: -12, right: 24,
          background: '#22c55e', color: '#fff',
          fontSize: 11, fontWeight: 800, padding: '4px 14px',
          borderRadius: 999, boxShadow: '0 4px 10px rgba(34,197,94,0.4)',
          letterSpacing: '0.05em'
        }}>WINNER</div>
      )}

      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <h4 style={{ fontSize: 18, fontWeight: 800, color: '#f8fafc', margin: 0, letterSpacing: '-0.02em' }}>{model.model_label}</h4>
        <span style={{ fontSize: 12, color: '#475569', fontWeight: 600 }}>{model.model_id}</span>
      </div>

      {/* Score ring */}
      <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 24 }}>
        <ScoreRing score={model.overall_score} size={110} label="Quality Index" />
      </div>

      {/* Dimension bars */}
      <div style={{ marginTop: 20 }}>
        {dims.map(dim => (
          <DimensionBar
            key={dim.name}
            dim={dim}
            winner={dimensionWinner[dim.name] === model.model_id}
          />
        ))}
      </div>

      {/* Stats Table */}
      <div style={{
        marginTop: 20, padding: 16, borderRadius: 14,
        background: 'rgba(15,23,42,0.5)', border: '1px solid rgba(148,163,184,0.1)',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#94a3b8', marginBottom: 8, fontWeight: 600 }}>
          <span>API Latency</span>
          <span style={{ fontFamily: 'monospace', color: '#f8fafc' }}>{model.latency_ms.toFixed(0)}ms</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#94a3b8', marginBottom: 8, fontWeight: 600 }}>
          <span>Corrections Applied</span>
          <span style={{ fontFamily: 'monospace', color: model.corrections_applied > 0 ? '#ef4444' : '#22c55e' }}>
            {model.corrections_applied}
          </span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#94a3b8', fontWeight: 600 }}>
          <span>Token Count</span>
          <span style={{ fontFamily: 'monospace', color: '#f8fafc' }}>{model.tokens_total}</span>
        </div>
      </div>

      {/* Response preview */}
      <div style={{ marginTop: 20 }}>
        <span style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#475569', fontWeight: 700 }}>
          Snapshot Output
        </span>
        <p style={{
          fontSize: 13, color: '#cbd5e1', lineHeight: 1.6,
          margin: '6px 0 0', maxHeight: 150, overflowY: 'auto',
          padding: 12, borderRadius: 10, background: 'rgba(15,23,42,0.6)',
          border: '1px solid rgba(148,163,184,0.1)',
          fontStyle: 'italic'
        }}>
          &ldquo;{model.response_text.slice(0, 500)}{model.response_text.length > 500 ? '…' : ''}&rdquo;
        </p>
      </div>
    </div>
  );
}

export default function EvalView({ result, progress, isLoading }: EvalViewProps) {
  if (isLoading || (!result && progress.length > 0)) {
    return (
      <div className="fade-in" style={{ padding: '24px 8px' }}>
        <p style={{ fontSize: 12, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em', color: '#8b5cf6', marginBottom: 16 }}>Evaluation Sequence</p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {progress.map((msg, i) => (
            <div key={i} className="fade-in" style={{
              display: 'flex', alignItems: 'center', gap: 12,
              fontSize: 14, color: '#cbd5e1', fontWeight: 500,
              padding: '12px 18px', borderRadius: 14,
              background: '#1e293b',
              border: '1px solid rgba(148,163,184,0.15)',
              boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)',
              transition: 'all 0.3s ease'
            }}>
              {i === progress.length - 1 && isLoading ? (
                <div className="spin" style={{
                  width: 14, height: 14, border: '2px solid rgba(139,92,246,0.3)',
                  borderTopColor: '#8b5cf6', borderRadius: '50%',
                  display: 'inline-block', flexShrink: 0,
                }} />
              ) : (
                <span style={{ color: '#22c55e', flexShrink: 0, fontSize: 16 }}>✓</span>
              )}
              {msg}
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (!result) return null;

  return (
    <div className="fade-in" style={{ padding: '8px 0' }}>
      {/* Verdict banner */}
      <div style={{
        borderRadius: 20, padding: '24px 32px', marginBottom: 24,
        background: 'linear-gradient(135deg, rgba(34,197,94,0.1), rgba(59,130,246,0.1))',
        border: '1px solid rgba(34,197,94,0.3)',
        boxShadow: '0 10px 25px -5px rgba(34,197,94,0.15)',
        position: 'relative',
        overflow: 'hidden'
      }}>
        {/* Glow Background Effect */}
        <div style={{ position: 'absolute', top: -50, right: -50, width: 150, height: 150, background: 'rgba(34,197,94,0.05)', borderRadius: '50%', filter: 'blur(50px)' }} />
        
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
          <div style={{ fontSize: 32 }}>🏆</div>
          <div>
            <p style={{ fontSize: 12, fontWeight: 700, textTransform: 'uppercase', color: '#22c55e', letterSpacing: '0.1em', margin: 0 }}>Final Verdict</p>
            <h2 style={{ fontSize: 24, fontWeight: 800, color: '#f8fafc', margin: 0, letterSpacing: '-0.02em' }}>
              {result.winner.replace('gemini-', 'Gemini ').replace('-', ' ')}
            </h2>
          </div>
        </div>
        <p style={{ fontSize: 16, color: '#f1f5f9', fontWeight: 600, margin: 0, lineHeight: 1.5, borderLeft: '4px solid #22c55e', paddingLeft: 16 }}>
          {result.verdict}
        </p>
        {result.rationale && (
          <p style={{ fontSize: 14, color: '#94a3b8', margin: '14px 0 0', lineHeight: 1.6, fontWeight: 500 }}>
            {result.rationale}
          </p>
        )}
      </div>

      {/* Model cards side by side */}
      <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
        {result.models.map(model => (
          <ModelCard
            key={model.model_id}
            model={model}
            isWinner={model.model_id === result.winner}
            dimensionWinner={result.dimension_winner}
          />
        ))}
      </div>
    </div>
  );
}
