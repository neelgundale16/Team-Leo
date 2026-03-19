'use client';

import { Token } from '@/types';

interface TokenStreamProps {
  tokens: Token[];
  isStreaming: boolean;
}

function CorrectedToken({ token }: { token: Token }) {
  return (
    <span className="token-corrected-wrapper">
      <span className="token-original-strike">{token.text}</span>
      <span className="token-corrected group">
        {token.correction ?? token.text}
        <span className="token-tooltip">
          <span className="tooltip-icon">✓</span>
          Auto-Corrected via:{' '}
          <span className="tooltip-source">{token.source ?? 'verified source'}</span>
        </span>
      </span>
    </span>
  );
}

export default function TokenStream({ tokens, isStreaming }: TokenStreamProps) {
  if (tokens.length === 0 && !isStreaming) {
    return (
      <div className="stream-empty">
        <div className="empty-grid" aria-hidden="true">
          {Array.from({ length: 48 }).map((_, i) => (
            <span key={i} className="grid-dot" />
          ))}
        </div>
        <p className="empty-label">Firewall standing by.</p>
        <p className="empty-sub">Submit a query to begin interception.</p>
      </div>
    );
  }

  return (
    <div className="token-stream-container">
      <div className="token-stream-output">
        {tokens.map((token) => {
          if (token.status === 'corrected') {
            return <CorrectedToken key={token.id} token={token} />;
          }
          return (
            <span
              key={token.id}
              className={`token-base token-fade-in ${
                token.status === 'streaming' ? 'token-streaming' : ''
              }`}
            >
              {token.text}
            </span>
          );
        })}
        {isStreaming && <span className="cursor-blink" aria-hidden="true" />}
      </div>
    </div>
  );
}