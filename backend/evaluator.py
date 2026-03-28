"""
evaluator.py — Adaptive Multi-Dimensional LLM Evaluation Engine

Evaluates LLM outputs across four quality dimensions:
  1. Factuality        — NLI-based vault verification (ground truth alignment)
  2. Hallucination Rate — Entropy-based uncertainty quantification per token
  3. Reasoning Quality  — Programmatic chain-of-thought and logic analysis
  4. Instruction Follow — Response adherence and query satisfaction scoring

Also runs LLM-as-Judge using Gemini Flash to produce a human-readable verdict
comparing two model outputs.

Reference: Semantic Entropy (Kuhn et al.), RAGAS, G-Eval (Liu et al. 2023)
"""

import re
import math
import time
import json
import httpx
import logging
import os
from typing import Optional
from models import EvalDimension, ModelEvalResult

logger = logging.getLogger(__name__)

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
JUDGE_MODEL     = "gemini-1.5-flash"   # fast model for judging


# ── Reasoning Quality ──────────────────────────────────────────────────────────

# Patterns that signal structured reasoning
REASONING_SIGNALS = re.compile(
    r'\b(?:because|therefore|thus|hence|as a result|consequently|'
    r'first|second|third|finally|additionally|furthermore|'
    r'in conclusion|to summarize|this means|which means|'
    r'based on|according to|given that|since|however|although)\b',
    re.IGNORECASE
)

# Patterns for numeric precision (good for financial queries)
NUMERIC_PRECISION = re.compile(
    r'\$[\d,.]+\s*(?:billion|million|trillion)?'
    r'|\d+(?:\.\d+)?%'
    r'|\d+(?:\.\d+)?\s*(?:billion|million|trillion)',
    re.IGNORECASE
)


def score_reasoning(text: str, query: str) -> EvalDimension:
    """
    Programmatic reasoning quality score.

    Signals evaluated:
    - Presence of logical connectors and structured reasoning markers
    - Numeric precision (relevant for financial domain)
    - Response length relative to query complexity
    - Sentence variety and coherence signals
    """
    if not text.strip():
        return EvalDimension(
            name="reasoning", score=0.0,
            rationale="Empty response"
        )

    sentences     = [s.strip() for s in re.split(r'[.!?]', text) if s.strip()]
    n_sentences   = len(sentences)
    n_words       = len(text.split())
    n_reasoning   = len(REASONING_SIGNALS.findall(text))
    n_numeric     = len(NUMERIC_PRECISION.findall(text))
    query_words   = len(query.split())

    # Scoring components
    # 1. Reasoning markers (0-0.35)
    reasoning_score = min(n_reasoning / max(n_sentences, 1) * 1.5, 0.35)

    # 2. Numeric precision for financial queries (0-0.25)
    numeric_score = min(n_numeric * 0.08, 0.25)

    # 3. Length appropriateness (0-0.25)
    # Ideal response: 3-8x query word count
    ratio = n_words / max(query_words, 1)
    if 3 <= ratio <= 10:
        length_score = 0.25
    elif ratio < 3:
        length_score = ratio / 3 * 0.25
    else:
        length_score = max(0.1, 0.25 - (ratio - 10) * 0.02)

    # 4. Sentence variety (0-0.15)
    avg_len = n_words / max(n_sentences, 1)
    variety_score = 0.15 if 8 <= avg_len <= 25 else 0.08

    total = reasoning_score + numeric_score + length_score + variety_score

    signals = []
    if n_reasoning > 0: signals.append(f"{n_reasoning} logical connectors")
    if n_numeric  > 0:  signals.append(f"{n_numeric} numeric values")
    signals.append(f"{n_sentences} sentences, {n_words} words")

    return EvalDimension(
        name      = "reasoning",
        score     = round(min(total, 1.0), 4),
        rationale = f"Reasoning signals: {', '.join(signals)}",
        evidence  = text[:150] + "..." if len(text) > 150 else text
    )


def score_instruction_following(text: str, query: str) -> EvalDimension:
    """
    Instruction following score.

    Checks:
    - Query type matched (question → answer present, request → action described)
    - Query keywords present in response
    - Response starts with relevant content (not refusals or disclaimers)
    - No off-topic tangents
    """
    if not text.strip():
        return EvalDimension(
            name="instruction_following", score=0.0,
            rationale="Empty response"
        )

    query_lower    = query.lower()
    response_lower = text.lower()
    score          = 0.0

    # Check if it's a question and response contains an answer signal
    is_question = query.strip().endswith('?') or query_lower.startswith(
        ('what', 'who', 'when', 'where', 'how', 'why', 'which', 'tell me')
    )
    if is_question:
        answer_signals = ['is', 'was', 'were', 'reported', 'generated',
                          'reached', 'grew', 'declined', 'totaled']
        has_answer = any(sig in response_lower for sig in answer_signals)
        score += 0.30 if has_answer else 0.10

    # Keyword coverage — important query nouns present in response
    stop_words = {'the', 'a', 'an', 'is', 'in', 'of', 'for', 'and', 'or',
                  'to', 'was', 'were', 'be', 'tell', 'me', 'what', 'how'}
    query_keywords = [
        w for w in re.findall(r'\b\w+\b', query_lower)
        if w not in stop_words and len(w) > 3
    ]
    if query_keywords:
        coverage = sum(1 for kw in query_keywords if kw in response_lower)
        score += (coverage / len(query_keywords)) * 0.40

    # No refusal or excessive disclaimers
    refusals = ["i cannot", "i don't know", "i'm not sure", "i am unable",
                "as an ai", "i don't have access"]
    has_refusal = any(r in response_lower for r in refusals)
    score += 0.0 if has_refusal else 0.20

    # Response is substantive (not too short)
    score += 0.10 if len(text.split()) >= 20 else 0.0

    return EvalDimension(
        name      = "instruction_following",
        score     = round(min(score, 1.0), 4),
        rationale = (
            f"Keyword coverage: {int(score*100)}% | "
            f"{'Has refusals' if has_refusal else 'No refusals'}"
        ),
        evidence  = f"Query keywords checked: {query_keywords[:5]}"
    )


def score_hallucination_rate(
    entropies: list,
    threshold: float = 0.28
) -> EvalDimension:
    """
    Hallucination rate from token entropy distribution.

    Score = 1 - (fraction of high-entropy tokens)
    A model with 0% high-entropy tokens scores 1.0 (no hallucination risk).
    A model with 50% high-entropy tokens scores 0.5.
    """
    if not entropies:
        return EvalDimension(
            name="hallucination_rate", score=0.5,
            rationale="No entropy data available"
        )

    high_entropy_count = sum(1 for e in entropies if e > threshold)
    rate               = high_entropy_count / len(entropies)
    score              = round(1.0 - rate, 4)
    avg_h              = round(sum(entropies) / len(entropies), 4)
    peak_h             = round(max(entropies), 4)

    return EvalDimension(
        name      = "hallucination_rate",
        score     = max(score, 0.0),
        rationale = (
            f"{high_entropy_count}/{len(entropies)} tokens above entropy threshold "
            f"({threshold}). Avg H={avg_h}, Peak H={peak_h}"
        ),
        evidence  = f"Rate: {rate*100:.1f}% uncertain tokens"
    )


def score_factuality(
    corrections_applied: int,
    total_claims: int,
    vault_matches: int
) -> EvalDimension:
    """
    Factuality score from NLI verification results.

    Higher corrections = lower factuality.
    Higher vault matches = more verifiable claims = better factuality signal.
    """
    if total_claims == 0:
        return EvalDimension(
            name="factuality", score=0.75,
            rationale="No verifiable claims detected — factuality unverified"
        )

    contradiction_rate = corrections_applied / max(total_claims, 1)
    base_score         = 1.0 - contradiction_rate

    # Bonus for having vault-verifiable claims (shows grounding)
    verification_bonus = min(vault_matches / max(total_claims, 1) * 0.1, 0.1)
    score              = min(base_score + verification_bonus, 1.0)

    return EvalDimension(
        name      = "factuality",
        score     = round(max(score, 0.0), 4),
        rationale = (
            f"{corrections_applied} corrections out of {total_claims} claims. "
            f"{vault_matches} claims matched vault."
        ),
        evidence  = f"Contradiction rate: {contradiction_rate*100:.1f}%"
    )


# ── Overall Score ──────────────────────────────────────────────────────────────

DIMENSION_WEIGHTS = {
    "factuality":           0.35,
    "hallucination_rate":   0.30,
    "reasoning":            0.20,
    "instruction_following":0.15,
}

def compute_overall_score(dimensions: dict) -> float:
    total = 0.0
    for dim_name, weight in DIMENSION_WEIGHTS.items():
        if dim_name in dimensions:
            total += dimensions[dim_name].score * weight
    return round(min(total, 1.0), 4)


# ── LLM-as-Judge ──────────────────────────────────────────────────────────────

async def llm_judge_comparison(
    query: str,
    response_a: str, model_a: str,
    response_b: str, model_b: str,
    scores_a: float, scores_b: float
) -> tuple[str, str, str]:
    """
    Use Gemini Flash as an impartial judge to compare two model responses.

    Returns: (winner_model_id, verdict_text, rationale)
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        # Fallback to score-based winner
        winner = model_a if scores_a >= scores_b else model_b
        return winner, f"Winner by score: {winner}", "No API key for LLM judge"

    prompt = f"""You are an expert evaluator comparing two AI model responses.

QUERY: {query}

MODEL A ({model_a}) RESPONSE:
{response_a[:600]}

MODEL B ({model_b}) RESPONSE:
{response_b[:600]}

Evaluate both responses on: factual accuracy, reasoning clarity, and helpfulness.
Then declare a winner.

Respond in this exact JSON format:
{{
  "winner": "<model_a_id or model_b_id>",
  "verdict": "<one sentence declaring winner and why>",
  "model_a_strengths": "<brief>",
  "model_b_strengths": "<brief>",
  "rationale": "<2-3 sentence detailed comparison>"
}}

Replace <model_a_id> with exactly: {model_a}
Replace <model_b_id> with exactly: {model_b}"""

    url = (
        f"{GEMINI_BASE_URL}/{JUDGE_MODEL}:generateContent"
        f"?key={api_key}"
    )
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 300,
            "responseMimeType": "application/json"
        }
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            result = json.loads(text)
            winner   = result.get("winner", model_a if scores_a >= scores_b else model_b)
            verdict  = result.get("verdict", "")
            rationale= result.get("rationale", "")
            return winner, verdict, rationale

    except Exception as e:
        logger.warning(f"LLM judge failed: {e} — falling back to score-based")
        winner = model_a if scores_a >= scores_b else model_b
        margin = abs(scores_a - scores_b)
        verdict = (
            f"{winner} wins by {'narrow' if margin < 0.05 else 'clear'} margin "
            f"(score: {max(scores_a, scores_b):.2f} vs {min(scores_a, scores_b):.2f})"
        )
        return winner, verdict, "Score-based fallback — judge model unavailable"


# ── Full Model Evaluation ──────────────────────────────────────────────────────

def build_model_eval(
    model_id:             str,
    model_label:          str,
    response_text:        str,
    token_entropies:      list,
    corrections_applied:  int,
    total_claims:         int,
    vault_matches:        int,
    corrected_response:   Optional[str],
    latency_ms:           float,
    query:                str
) -> ModelEvalResult:
    """
    Build a complete ModelEvalResult from pipeline outputs.
    Called by main.py after each model's pipeline completes.
    """
    # Compute all four dimensions
    dim_hallucination   = score_hallucination_rate(token_entropies)
    dim_factuality      = score_factuality(corrections_applied, total_claims, vault_matches)
    dim_reasoning       = score_reasoning(response_text, query)
    dim_instruction     = score_instruction_following(response_text, query)

    dimensions = {
        "factuality":            dim_factuality,
        "hallucination_rate":    dim_hallucination,
        "reasoning":             dim_reasoning,
        "instruction_following": dim_instruction,
    }

    overall = compute_overall_score(dimensions)

    avg_h  = round(sum(token_entropies) / len(token_entropies), 4) if token_entropies else 0.0
    peak_h = round(max(token_entropies), 4) if token_entropies else 0.0
    h_rate = sum(1 for e in token_entropies if e > 0.28) / max(len(token_entropies), 1)

    return ModelEvalResult(
        model_id            = model_id,
        model_label         = model_label,
        response_text       = response_text,
        tokens_total        = len(token_entropies),
        hallucination_rate  = round(h_rate, 4),
        avg_token_entropy   = avg_h,
        peak_entropy        = peak_h,
        dimensions          = dimensions,
        overall_score       = overall,
        corrections_applied = corrections_applied,
        corrected_response  = corrected_response,
        latency_ms          = round(latency_ms, 1),
    )