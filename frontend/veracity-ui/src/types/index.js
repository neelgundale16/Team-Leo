export interface Token {
  id: string;
  text: string;
  status: 'streaming' | 'verified' | 'corrected' | 'skipped';
  correction?: string;
  source?: string;
  timestamp: number;
}

export interface StreamEvent {
  event_type: 'token' | 'correction' | 'stats' | 'done' | 'error';
  data: Record<string, any>;
}

export interface SessionStats {
  total_claims_detected: number;
  claims_verified: number;
  claims_skipped: number;
  hallucinations_found: number;
  corrections_made: number;
  avg_verification_latency_ms: number;
  total_pipeline_latency_ms: number;
}

export interface CorrectionEvent {
  id: string;
  original: string;
  corrected: string;
  source: string;
  diff_ratio: number;
}