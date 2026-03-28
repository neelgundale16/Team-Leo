"""
interceptor.py — Gemini Streaming Interceptor with Logprob Entropy Detection

Uses Google Gemini API with responseLogprobs=true to get per-token log
probabilities. Shannon entropy H(t) = -p*log(p) is computed per token.

High-entropy spans = model was uncertain = hallucination candidate.

Supports two Gemini models simultaneously for comparison mode.
"""

import re
import json
import math
import httpx
import asyncio
import logging
import os
from collections import deque
from typing import AsyncGenerator
from models import Claim

logger = logging.getLogger(__name__)

# ── Gemini Config ──────────────────────────────────────────────────────────────
GEMINI_BASE_URL   = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_MODELS     = {
    "gemini-1.5-flash":      "gemini-1.5-flash",
    "gemini-2.0-flash-lite": "gemini-2.0-flash-lite",
    "gemini-1.5-pro":        "gemini-1.5-pro",
    "gemini-2.0-flash":      "gemini-2.0-flash",
}
DEFAULT_MODEL     = "gemini-1.5-flash"

# ── Entropy Thresholds ─────────────────────────────────────────────────────────
# H(t) = -p*log(p), peaks at p=1/e ≈ 0.368 with H≈0.368
# Tokens the model was uncertain about → H > threshold
ENTROPY_THRESHOLD = 0.28
WINDOW_SIZE       = 6
BURST_MIN_TOKENS  = 2

# ── Sentence boundary ──────────────────────────────────────────────────────────
SENTENCE_END = re.compile(r'(?<=[.!?])\s+')


# ── Entropy calculation ────────────────────────────────────────────────────────
def compute_entropy(log_probability: float) -> float:
    """
    Single-token Shannon entropy from Gemini logprob.
    H(t) = -p * log(p)  where p = exp(logprob)
    Higher = model was uncertain at this token position.
    """
    if log_probability is None:
        return 0.0
    p = math.exp(max(float(log_probability), -20.0))
    return round(-p * math.log(p + 1e-12), 6)


def smooth_entropy(window: deque) -> float:
    return sum(window) / len(window) if window else 0.0


# ── Claim detection ────────────────────────────────────────────────────────────
def detect_claim_from_span(
    span_tokens: list, span_entropies: list,
    sentence: str, position: int
) -> Claim | None:
    text = "".join(span_tokens).strip()
    if not text:
        return None
    avg_h = sum(span_entropies) / len(span_entropies)
    if avg_h > 0.33:   claim_type = "statistic"
    elif avg_h > 0.31: claim_type = "number"
    elif avg_h > 0.29: claim_type = "name"
    elif avg_h > 0.28: claim_type = "date"
    else:              claim_type = "general"
    return Claim(
        text=text, type=claim_type,
        position=position, sentence=sentence.strip(),
        entropy=round(avg_h, 4)
    )


def extract_claims_from_entropy(
    tokens: list, entropies: list, sentence: str
) -> list:
    if not tokens or not entropies:
        return []
    claims, in_span = [], False
    span_tokens, span_entropies, span_start = [], [], 0

    for i, (tok, ent) in enumerate(zip(tokens, entropies)):
        if ent > ENTROPY_THRESHOLD:
            if not in_span:
                in_span, span_start = True, i
                span_tokens, span_entropies = [tok], [ent]
            else:
                span_tokens.append(tok)
                span_entropies.append(ent)
        else:
            if in_span and len(span_tokens) >= BURST_MIN_TOKENS:
                c = detect_claim_from_span(span_tokens, span_entropies, sentence, span_start)
                if c: claims.append(c)
            in_span, span_tokens, span_entropies = False, [], []

    if in_span and len(span_tokens) >= BURST_MIN_TOKENS:
        c = detect_claim_from_span(span_tokens, span_entropies, sentence, span_start)
        if c: claims.append(c)

    return claims


# ── Gemini Streaming ───────────────────────────────────────────────────────────
async def _stream_gemini(
    query: str,
    model_id: str = DEFAULT_MODEL,
    system_prompt: str = (
        "You are a financial analysis assistant. "
        "Answer questions about company financials, market data, "
        "and economic indicators using specific numbers, percentages, and statistics."
    )
) -> AsyncGenerator[tuple, None]:
    """
    Stream tokens from Gemini API with per-token log probabilities.

    Gemini API returns logprobsResult per candidate with:
      chosenCandidates[].logProbability  — log prob of chosen token
      topCandidates[].logProbability     — top-k alternatives

    We use chosenCandidates logProbability for entropy computation.
    Yields: (token_text, entropy) tuples
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY not set. "
            "Get a free key at aistudio.google.com and add to backend/.env"
        )

    model_name = GEMINI_MODELS.get(model_id, model_id)
    url        = (
        f"{GEMINI_BASE_URL}/{model_name}:streamGenerateContent"
        f"?key={api_key}&alt=sse"
    )

    payload = {
        "system_instruction": {
            "parts": [{"text": system_prompt}]
        },
        "contents": [
            {"role": "user", "parts": [{"text": query}]}
        ],
        "generationConfig": {
            "temperature":       0.7,
            "maxOutputTokens":   600,
            "responseLogprobs":  True,
            "logprobs":          5,
        }
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream("POST", url, json=payload) as response:
            if response.status_code != 200:
                body = await response.aread()
                raise httpx.HTTPStatusError(
                    f"Gemini {model_id} returned {response.status_code}: "
                    f"{body.decode()[:300]}",
                    request=response.request, response=response
                )

            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:].strip()
                if not data_str or data_str == "[DONE]":
                    continue

                try:
                    chunk = json.loads(data_str)
                    candidates = chunk.get("candidates", [])
                    if not candidates:
                        continue

                    candidate = candidates[0]
                    parts     = candidate.get("content", {}).get("parts", [])
                    text      = "".join(p.get("text", "") for p in parts)
                    if not text:
                        continue

                    # Extract entropy from logprobs
                    entropy       = 0.0
                    logprobs_data = candidate.get("logprobsResult", {})
                    chosen        = logprobs_data.get("chosenCandidates", [])
                    if chosen:
                        lp = chosen[0].get("logProbability")
                        if lp is not None:
                            entropy = compute_entropy(lp)

                    yield (text, entropy)

                except (json.JSONDecodeError, KeyError, IndexError):
                    continue


# ── Mock Stream ────────────────────────────────────────────────────────────────
async def _stream_mock(
    query: str,
    model_id: str = DEFAULT_MODEL
) -> AsyncGenerator[tuple, None]:
    """
    Offline mock with synthetic entropy — for demo without API key.
    Set USE_MOCK=true in .env
    """
    # Different hallucinations per model for realistic comparison demo
    if "flash-lite" in model_id or "2.0" in model_id:
        tokens = [
            ("Apple", 0.04), (" reported", 0.07), (" revenue", 0.08), (" of", 0.05),
            (" $", 0.20), ("412", 0.33), (" billion", 0.30),   # hallucinated
            (" in", 0.04), (" FY", 0.08), ("2022", 0.10), (".", 0.02), (" ",  0.01),
            ("Tesla", 0.05), (" delivered", 0.07),
            (" 1.9", 0.29), (" million", 0.31),                 # hallucinated
            (" vehicles", 0.06), (" in", 0.04), (" 2023", 0.09), (".", 0.02),
        ]
    else:
        tokens = [
            ("Apple", 0.04), (" Inc", 0.05), (" reported", 0.07),
            (" revenue", 0.08), (" of", 0.05),
            (" $", 0.21), ("523", 0.35), (" billion", 0.32),   # hallucinated
            (" in", 0.04), (" fiscal", 0.06), (" year", 0.05), (" 2022", 0.11),
            (".", 0.02), (" ", 0.01),
            ("Microsoft", 0.05), (" Azure", 0.06), (" grew", 0.08),
            (" 45", 0.34), ("%", 0.32),                        # hallucinated
            (" in", 0.04), (" Q4", 0.09), (" 2023", 0.10), (".", 0.02),
        ]
    for tok, ent in tokens:
        yield (tok, ent)
        await asyncio.sleep(0.04)


# ── Core Generator ─────────────────────────────────────────────────────────────
async def stream_and_detect(
    query: str,
    model_id: str = DEFAULT_MODEL
) -> AsyncGenerator[tuple, None]:
    """
    Main interceptor generator.

    Yields:
      ("TOKEN:<text>|<entropy>", [])    raw token + entropy for frontend heatmap
      ("<sentence>", [Claim, ...])       completed sentence with detected claims
      ("ERROR:<msg>", [])               on failure
    """
    use_mock       = os.getenv("USE_MOCK", "false").lower() == "true"
    text_buffer    = ""
    token_buffer   = []
    entropy_buffer = []
    entropy_window = deque(maxlen=WINDOW_SIZE)
    token_count    = 0
    stream_fn      = _stream_mock if use_mock else _stream_gemini

    try:
        async for token, entropy in stream_fn(query, model_id):
            token_count    += 1
            text_buffer    += token
            token_buffer   .append(token)
            entropy_buffer .append(entropy)
            entropy_window .append(entropy)

            # Yield raw token with entropy for frontend heatmap
            yield (f"TOKEN:{token}|{entropy:.4f}", [])

            # Detect completed sentences
            parts = SENTENCE_END.split(text_buffer)
            if len(parts) > 1:
                for sentence in parts[:-1]:
                    sentence = sentence.strip()
                    if not sentence:
                        continue

                    char_count = 0
                    s_tokens, s_entropies = [], []
                    for tok, ent in zip(token_buffer, entropy_buffer):
                        if char_count >= len(sentence):
                            break
                        s_tokens.append(tok)
                        s_entropies.append(ent)
                        char_count += len(tok)

                    claims = extract_claims_from_entropy(s_tokens, s_entropies, sentence)
                    logger.debug(
                        f"[{model_id}] Sentence: '{sentence[:50]}' | "
                        f"Claims: {len(claims)} | "
                        f"Peak H: {max(s_entropies, default=0):.3f}"
                    )
                    yield (sentence, claims)

                text_buffer    = parts[-1]
                remaining_len  = len(text_buffer)
                char_count     = 0
                new_t, new_e   = [], []
                for tok, ent in zip(reversed(token_buffer), reversed(entropy_buffer)):
                    if char_count >= remaining_len:
                        break
                    new_t.insert(0, tok)
                    new_e.insert(0, ent)
                    char_count += len(tok)
                token_buffer   = new_t
                entropy_buffer = new_e

        if text_buffer.strip():
            claims = extract_claims_from_entropy(
                token_buffer, entropy_buffer, text_buffer.strip()
            )
            yield (text_buffer.strip(), claims)

    except ValueError as e:
        logger.error(f"Config error: {e}")
        yield (f"ERROR:{e}", [])
    except httpx.HTTPStatusError as e:
        logger.error(f"Gemini API error: {e}")
        yield (f"ERROR:{e}", [])
    except httpx.ConnectError:
        logger.error("Cannot reach Gemini API")
        yield ("ERROR:Cannot reach Gemini API. Check internet connection.", [])
    except Exception as e:
        logger.error(f"Interceptor error: {e}", exc_info=True)
        yield (f"ERROR:{e}", [])

    logger.info(f"[{model_id}] Stream complete | tokens: {token_count}")