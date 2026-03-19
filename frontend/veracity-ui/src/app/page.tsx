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
      let response: Response;

      if (attachments.length > 0) {
        const form = new FormData();
        form.append('query', query);
        attachments.forEach(({ file }) => form.append('files', file));
        response = await fetch('http://localhost:8000/chat', { method: 'POST', body: form });
      } else {
        response = await fetch('http://localhost:8000/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query }),
        });
      }

      if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      if (!response.body)  throw new Error('No response body received');

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
                setTokens((p) => [...p, {
                  id: data.id, text: data.text,
                  status: data.status ?? 'streaming', timestamp: Date.now(),
                }]);
              } else if (event_type === 'correction') {
                setTokens((p) => p.map((t) =>
                  t.id === data.id
                    ? { ...t, status: 'corrected', correction: data.corrected, source: data.source }
                    : t
                ));
              } else if (event_type === 'stats') {
                setStats(data as SessionStats);
              } else if (event_type === 'done') {
                if (data?.session_stats) setStats(data.session_stats);
                setIsStreaming(false);
              } else if (event_type === 'error') {
                setError(data?.message ?? 'Unknown error');
                setIsStreaming(false);
              }
            } catch { /* malformed line — skip */ }
          }
        }
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Connection failed');
    } finally {
      setIsStreaming(false);
    }
  }, []);

  const showStats = isStreaming || stats !== null || tokens.some(t => t.status === 'corrected');

  return (
    <div className="app-shell">

      {/* ── Topbar ──────────────────────────────────── */}
      <header className="topbar">
        <div className="topbar-inner">
          {/* Logo mark */}
          <div className="logo-mark">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
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
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
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
          <span className="footer-left">XEN-O-THON 2026 · Team Leo · AI &amp; Automation — Beyond Wrappers</span>
          <span className="footer-right">GTBIT New Delhi · Institution's Innovation Council</span>
        </div>
      </footer>

    </div>
  );
}