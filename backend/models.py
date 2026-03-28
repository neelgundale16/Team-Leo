"""
models.py — Pydantic schemas for Veracity AI
Covers both self-healing firewall AND adaptive evaluation framework.
"""
from pydantic import BaseModel, Field
from typing import Optional, Literal, List, Dict
from datetime import datetime


# ── Request Models ─────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    query: str = Field(..., description="User query")
    session_id: Optional[str] = None
    models: Optional[List[str]] = Field(
        default=["gemini-1.5-flash", "gemini-2.0-flash-lite"],
        description="Models to evaluate against each other"
    )
    eval_mode: bool = Field(
        default=False,
        description="Run full multi-model evaluation framework"
    )


# ── Claim Detection ────────────────────────────────────────────────────────────

class Claim(BaseModel):
    text: str
    type: Literal["number", "name", "date", "policy", "statistic", "general"] = "general"
    position: int
    sentence: str
    entropy: float = 0.0


# ── Vault ──────────────────────────────────────────────────────────────────────

class VaultResult(BaseModel):
    matched_text: str
    source_document: str
    similarity_score: float
    distance: float


# ── NLI ───────────────────────────────────────────────────────────────────────

class NLIResult(BaseModel):
    label: Literal["entailment", "neutral", "contradiction"]
    confidence: float
    entailment_score: float
    neutral_score: float
    contradiction_score: float
    is_hallucination: bool


# ── Token Stream ───────────────────────────────────────────────────────────────

class StreamToken(BaseModel):
    id: str
    text: str
    status: Literal["streaming", "verified", "corrected", "skipped", "high_entropy"] = "streaming"
    entropy: float = 0.0
    correction: Optional[str] = None
    source: Optional[str] = None
    timestamp: float = Field(default_factory=lambda: datetime.now().timestamp())


# ── Evaluation Dimensions ──────────────────────────────────────────────────────

class EvalDimension(BaseModel):
    name: str
    score: float = Field(..., ge=0.0, le=1.0, description="Score 0-1")
    rationale: str
    evidence: Optional[str] = None


class ModelEvalResult(BaseModel):
    model_id: str
    model_label: str
    response_text: str
    tokens_total: int
    hallucination_rate: float          # % high-entropy tokens
    avg_token_entropy: float
    peak_entropy: float
    dimensions: Dict[str, EvalDimension]  # factuality, reasoning, instruction_following, coherence
    overall_score: float
    corrections_applied: int
    corrected_response: Optional[str] = None
    latency_ms: float
    judge_verdict: Optional[str] = None   # LLM-as-judge summary


class ComparisonResult(BaseModel):
    query: str
    session_id: str
    models: List[ModelEvalResult]
    winner: str                           # model_id of winner
    winner_rationale: str
    dimension_winner: Dict[str, str]      # per-dimension winners
    timestamp: float = Field(default_factory=lambda: datetime.now().timestamp())


# ── Session Stats ──────────────────────────────────────────────────────────────

class SessionStats(BaseModel):
    total_claims_detected: int = 0
    claims_verified: int = 0
    claims_skipped: int = 0
    hallucinations_found: int = 0
    corrections_made: int = 0
    avg_verification_latency_ms: float = 0.0
    total_pipeline_latency_ms: float = 0.0
    model_id: Optional[str] = None


# ── SSE Events ─────────────────────────────────────────────────────────────────

class SSEEvent(BaseModel):
    event_type: Literal[
        "token", "correction", "stats", "done", "error",
        "eval_start", "eval_progress", "eval_complete", "model_done"
    ]
    data: dict
    model_id: Optional[str] = None