'use client';

import { Token } from '@/types';

interface TokenStreamProps {
  tokens: Token[];
  isStreaming: boolean;
}

function CorrectedToken({ token }: { token: Token }) {
  return (
    <span className="token-corrected-wrap">
      <span className="token-original">{token.text}</span>
      <span className="token-corrected">
        {token.correction ?? token.text}
        <span className="token-tooltip">
          ✓ Auto-Corrected via:{' '}
          <span className="tooltip-source">{token.source ?? 'verified source'}</span>
        </span>
      </span>
    </span>
  );
}

export default function TokenStream({ tokens, isStreaming }: TokenStreamProps) {
  if (tokens.length === 0 && !isStreaming) {
    return (
      <div className="stream-card">
        <div className="card-header">
          <div className="card-icon card-icon-red">🛡️</div>
          <span className="card-title">Response Output</span>
          <span className="card-subtitle">Hallucination firewall active</span>
        </div>
        <div className="stream-body">
          <div className="stream-empty">
            <div className="empty-illustration">⚡</div>
            <p className="empty-title">Firewall Standing By</p>
            <p className="empty-sub">
              Submit a query above. The AI response will stream here token-by-token,
              with any hallucinations auto-corrected in real time.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="stream-card">
      <div className="card-header">
        <div className="card-icon card-icon-red">🛡️</div>
        <span className="card-title">Response Output</span>
        {isStreaming && (
          <span className="card-subtitle" style={{ color: 'var(--green)', display: 'flex', alignItems: 'center', gap: '5px' }}>
            <span className="status-dot" style={{ width: '6px', height: '6px', background: 'var(--green-mid)', borderRadius: '50%', animation: 'pulse-green 1.5s ease-in-out infinite', display: 'inline-block' }} />
            Streaming
          </span>
        )}
        {!isStreaming && tokens.length > 0 && (
          <span className="card-subtitle">
            {tokens.filter(t => t.status === 'corrected').length > 0
              ? `${tokens.filter(t => t.status === 'corrected').length} correction(s) applied`
              : 'No hallucinations detected'}
          </span>
        )}
      </div>
      <div className="stream-body">
        <div className="token-output">
          {tokens.map((token) =>
            token.status === 'corrected' ? (
              <CorrectedToken key={token.id} token={token} />
            ) : (
              <span key={token.id} className="token-base">{token.text}</span>
            )
          )}
          {isStreaming && <span className="cursor-blink" aria-hidden="true" />}
        </div>
      </div>
    </div>
  );
}