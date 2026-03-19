'use client';

import { useState, useCallback } from 'react';
import QueryInput, { AttachedFile } from '@/components/QueryInput';
import TokenStream from '@/components/TokenStream';
import StatsPanel from '@/components/StatsPanel';
import { Token, SessionStats } from '@/types';

export default function Home() {
  const [tokens, setTokens]          = useState<Token[]>([]);
  const [stats, setStats]            = useState<SessionStats | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError]            = useState<string | null>(null);

  const handleSubmit = useCallback(
    async (query: string, attachments: AttachedFile[]) => {
      // Reset state
      setTokens([]);
      setStats(null);
      setError(null);
      setIsStreaming(true);

      try {
        let response: Response;

        if (attachments.length > 0) {
          // ── Send as multipart/form-data so files reach the backend ──
          const form = new FormData();
          form.append('query', query);
          attachments.forEach(({ file }) => form.append('files', file));

          response = await fetch('http://localhost:8000/chat', {
            method: 'POST',
            // Do NOT set Content-Type — browser sets boundary automatically
            body: form,
          });
        } else {
          // ── Plain JSON (original behaviour) ──
          response = await fetch('http://localhost:8000/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query }),
          });
        }

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        if (!response.body) {
          throw new Error('No response body received');
        }

        const reader  = response.body.getReader();
        const decoder = new TextDecoder();
        let   buffer  = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });

          // SSE events are separated by "\n\n"
          const parts = buffer.split('\n\n');
          buffer = parts.pop() ?? '';

          for (const part of parts) {
            const lines = part.split('\n');
            for (const line of lines) {
              if (!line.startsWith('data: ')) continue;
              const jsonStr = line.slice(6).trim();
              if (!jsonStr || jsonStr === '[DONE]') continue;

              try {
                const event = JSON.parse(jsonStr);
                const { event_type, data } = event;

                if (event_type === 'token') {
                  const newToken: Token = {
                    id:        data.id,
                    text:      data.text,
                    status:    data.status ?? 'streaming',
                    timestamp: Date.now(),
                  };
                  setTokens((prev) => [...prev, newToken]);

                } else if (event_type === 'correction') {
                  setTokens((prev) =>
                    prev.map((t) =>
                      t.id === data.id
                        ? {
                            ...t,
                            status:     'corrected',
                            correction: data.corrected,
                            source:     data.source,
                          }
                        : t
                    )
                  );

                } else if (event_type === 'stats') {
                  setStats(data as SessionStats);

                } else if (event_type === 'done') {
                  if (data?.session_stats) {
                    setStats(data.session_stats as SessionStats);
                  }
                  setIsStreaming(false);

                } else if (event_type === 'error') {
                  setError(data?.message ?? 'Unknown error from server');
                  setIsStreaming(false);
                }
              } catch {
                // Malformed JSON line — skip
              }
            }
          }
        }
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : 'Connection failed';
        setError(msg);
      } finally {
        setIsStreaming(false);
      }
    },
    []
  );

  const correctionCount = tokens.filter((t) => t.status === 'corrected').length;

  return (
    <div className="app-root">
      {/* ── Header ───────────────────────────────────────── */}
      <header className="app-header">
        <span className="header-title">🛡️ Project Veracity</span>
        <span className="header-badge">FIREWALL ACTIVE</span>
        <span className="header-subtitle">
          XEN-O-THON 2026 &nbsp;·&nbsp; Team Leo &nbsp;·&nbsp; GTBIT New Delhi
        </span>
      </header>

      {/* ── Main ─────────────────────────────────────────── */}
      <main className="app-main">
        <section className="main-left">
          <QueryInput onSubmit={handleSubmit} isLoading={isStreaming} />

          {error && (
            <div className="error-banner">
              ⚠ ERROR &nbsp;—&nbsp; {error}
            </div>
          )}

          <TokenStream tokens={tokens} isStreaming={isStreaming} />
        </section>

        <StatsPanel
          stats={stats}
          isVisible={isStreaming || stats !== null || correctionCount > 0}
        />
      </main>

      {/* ── Footer ───────────────────────────────────────── */}
      <footer className="app-footer">
        <span>XEN-O-THON 2026 &nbsp;|&nbsp; Team Leo</span>
        <span>AI &amp; Automation — Beyond Wrappers</span>
      </footer>
    </div>
  );
}