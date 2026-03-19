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

  const handleSubmit = useCallback(async (query: string, attachments: AttachedFile[]) => {
    setTokens([]);
    setStats(null);
    setError(null);
    setIsStreaming(true);

    try {
      // ── Step 1: Upload any attached files to the vault first ──────────────
      if (attachments.length > 0) {
        for (const { file } of attachments) {
          const form = new FormData();
          form.append('file', file);
          form.append('source_name', file.name);

          let uploadRes: Response;
          try {
            uploadRes = await fetch('/api/vault/upload', {
              method: 'POST',
              body: form,
              // Do NOT set Content-Type — browser sets it with boundary automatically
            });
          } catch {
            throw new Error(
              `Cannot connect to the backend server. Make sure it is running on port 8000.\n` +
              `Run: uvicorn main:app --reload --port 8000`
            );
          }

          if (!uploadRes.ok) {
            let errDetail = `HTTP ${uploadRes.status}`;
            try {
              const errBody = await uploadRes.json();
              errDetail = errBody.detail ?? errBody.message ?? JSON.stringify(errBody);
            } catch {
              errDetail = await uploadRes.text().catch(() => `HTTP ${uploadRes.status}`);
            }
            throw new Error(`Upload failed for "${file.name}": ${errDetail}`);
          }

          const uploadData = await uploadRes.json();
          console.log(
            `✅ Vault upload: ${uploadData.filename} — ` +
            `${uploadData.chunks_added} chunks added. ` +
            `Vault total: ${uploadData.vault_total}. ` +
            `${uploadData.message ?? ''}`
          );
        }
      }

      // ── Step 2: Send the text query to the firewall pipeline ──────────────
      // If no query text but files were uploaded, use a default prompt
      const finalQuery = query.trim() ||
        `Summarize the key financial facts from the uploaded document.`;

      let response: Response;
      try {
        response = await fetch('/api/chat', {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({ query: finalQuery }),
        });
      } catch {
        throw new Error(
          `Cannot connect to the backend server. Make sure it is running on port 8000.\n` +
          `Run: uvicorn main:app --reload --port 8000`
        );
      }

      if (!response.ok) {
        let errDetail = `HTTP ${response.status}`;
        try {
          const errBody = await response.json();
          errDetail = errBody.detail ?? errBody.message ?? JSON.stringify(errBody);
        } catch {
          errDetail = await response.text().catch(() => `HTTP ${response.status}`);
        }
        throw new Error(`Backend error: ${errDetail}`);
      }
      if (!response.body) throw new Error('No response body received from server.');

      // ── Step 3: Read SSE stream ───────────────────────────────────────────
      const reader  = response.body.getReader();
      const decoder = new TextDecoder();
      let   buffer  = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop() ?? '';

        for (const part of parts) {
          for (const line of part.split('\n')) {
            if (!line.startsWith('data: ')) continue;
            const jsonStr = line.slice(6).trim();
            if (!jsonStr || jsonStr === '[DONE]') continue;

            try {
              const { event_type, data } = JSON.parse(jsonStr);

              if (event_type === 'token') {
                setTokens((prev) => [...prev, {
                  id:        data.id,
                  text:      data.text,
                  status:    data.status ?? 'streaming',
                  timestamp: Date.now(),
                }]);

              } else if (event_type === 'correction') {
                // Backend sends correction by sentence match, not token id
                // Mark the most recent token that contains the original claim
                setTokens((prev) => {
                  const updated  = [...prev];
                  let   matched  = false;

                  for (let i = updated.length - 1; i >= 0; i--) {
                    const windowText = updated
                      .slice(Math.max(0, i - 15), i + 1)
                      .map((t) => t.text)
                      .join('');

                    if (
                      windowText.includes(data.original_claim) ||
                      updated[i].text.includes(data.original_claim)
                    ) {
                      updated[i] = {
                        ...updated[i],
                        status:     'corrected',
                        correction: data.corrected_sentence,
                        source:     data.source,
                      };
                      matched = true;
                      break;
                    }
                  }

                  // Fallback: append correction as new token if not found inline
                  if (!matched) {
                    updated.push({
                      id:         `corr-${Date.now()}`,
                      text:       data.original_sentence ?? data.original_claim,
                      status:     'corrected',
                      correction: data.corrected_sentence,
                      source:     data.source,
                      timestamp:  Date.now(),
                    });
                  }

                  return updated;
                });

              } else if (event_type === 'stats') {
                setStats(data as SessionStats);

              } else if (event_type === 'done') {
                if (data?.total_corrections_made !== undefined) {
                  setStats(data as SessionStats);
                } else if (data) {
                  setStats(data as SessionStats);
                }
                setIsStreaming(false);

              } else if (event_type === 'error') {
                setError(data?.message ?? 'Unknown pipeline error');
                setIsStreaming(false);
              }

            } catch {
              // Malformed SSE line — skip silently
            }
          }
        }
      }

    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Connection failed. Is the backend running?');
    } finally {
      setIsStreaming(false);
    }
  }, []);

  const showStats = isStreaming || stats !== null || tokens.some((t) => t.status === 'corrected');

  return (
    <div className="app-shell">

      {/* ── Topbar ──────────────────────────────────── */}
      <header className="topbar">
        <div className="topbar-inner">
          <div className="logo-mark">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
              strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
            </svg>
          </div>

          <span className="brand-name">Project Veracity</span>
          <span className="brand-version">v1.0</span>

          <div className="topbar-divider" />
          <span className="topbar-meta">XEN-O-THON 2026 · Team Leo · GTBIT New Delhi</span>

          <div className="topbar-status">
            <span className="status-dot" />
            Firewall Active
          </div>
        </div>
      </header>

      {/* ── Page Body ───────────────────────────────── */}
      <div className="page-body">

        {/* Hero */}
        <div className="page-hero animate-in">
          <div className="hero-eyebrow">
            <span className="eyebrow-chip">AI &amp; Automation</span>
            <span className="eyebrow-sep">·</span>
            <span className="eyebrow-track">Beyond Wrappers Track</span>
          </div>
          <h1 className="hero-title">
            Self-Healing <span>Hallucination</span> Firewall
          </h1>
        </div>

        {/* Left column */}
        <section className="main-left animate-in" style={{ animationDelay: '0.05s' }}>
          <QueryInput onSubmit={handleSubmit} isLoading={isStreaming} />

          {error && (
            <div className="error-banner">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" strokeWidth="2.5"
                strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10"/>
                <line x1="12" y1="8"  x2="12"    y2="12"/>
                <line x1="12" y1="16" x2="12.01" y2="16"/>
              </svg>
              {error}
            </div>
          )}

          <TokenStream tokens={tokens} isStreaming={isStreaming} />
        </section>

        {/* Right column */}
        <StatsPanel stats={stats} isVisible={showStats} isStreaming={isStreaming} />
      </div>

      {/* ── Footer ──────────────────────────────────── */}
      <footer className="page-footer">
        <div className="footer-inner">
          <span className="footer-left">
            XEN-O-THON 2026 · Team Leo · AI &amp; Automation — Beyond Wrappers
          </span>
          <span className="footer-right">
            GTBIT New Delhi · Institution's Innovation Council
          </span>
        </div>
      </footer>

    </div>
  );
}
