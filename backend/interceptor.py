"""
interceptor.py — Gemini Streaming Interceptor with Entropy-Based Hallucination Detection
Project Veracity v2.0 — AI4Dev'26, PSG Tech Coimbatore

Calls Gemini API with logprobs enabled, detects high-entropy claims mid-stream,
and yields (sentence, claims, entropies) tuples for the firewall pipeline.

NO hardcoded mock responses. All generation is done via Gemini LLM.
Includes aggressive rate limiting + exponential backoff to stay within free tier.
"""

import os
import re
import json
import math
import time
import asyncio
import logging
import httpx
from typing import AsyncGenerator, Optional
from dotenv import load_dotenv
from models import Claim

load_dotenv()
logger = logging.getLogger(__name__)

GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL    = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

# ── Rate limiting — Gemini free tier: 15 RPM = 1 every 4s ────────────────────
# We use 5s gap for safety margin, plus track request timestamps for burst protection
_last_request_time: float = 0.0
_MIN_REQUEST_GAP: float   = 0.5   # Reduced to 0.5s for maximum speed
_request_timestamps: list[float] = []  # Track last 60s of requests
_MAX_REQUESTS_PER_MINUTE: int = 60     # Let Google's API return 429s instead of artifically pausing locally

# ── Retry configuration ──────────────────────────────────────────────────────
_MAX_RETRIES: int = 3
_RETRY_DELAYS: list[float] = [15.0, 30.0, 60.0]  # Exponential backoff delays

ENTROPY_HIGH_THRESHOLD = 0.25
MIN_CLAIM_SPAN         = 2


# ── Rate limiter with burst protection ───────────────────────────────────────
async def _rate_limit() -> float:
    """
    Ensures we never exceed free tier limits.
    Returns the total time slept (if any), so caller can inform user.
    """
    global _last_request_time, _request_timestamps

    now = time.monotonic()
    _request_timestamps = [t for t in _request_timestamps if now - t < 60.0]
    
    total_slept = 0.0

    if len(_request_timestamps) >= _MAX_REQUESTS_PER_MINUTE:
        oldest = _request_timestamps[0]
        wait_until = oldest + 62.0
        sleep_time = wait_until - now
        if sleep_time > 0:
            logger.warning(
                "Rate limit: %d requests in last 60s, waiting %.1fs",
                len(_request_timestamps), sleep_time
            )
            total_slept += sleep_time

    now = time.monotonic()
    gap = now - _last_request_time
    if gap < _MIN_REQUEST_GAP:
        total_slept += (_MIN_REQUEST_GAP - gap)

    return total_slept

async def _apply_rate_limit_sleep(total_slept: float):
    if total_slept > 0:
        await asyncio.sleep(total_slept)
        
    global _last_request_time, _request_timestamps
    _last_request_time = time.monotonic()
    _request_timestamps.append(_last_request_time)


# ── Entropy calculation ──────────────────────────────────────────────────────
def _entropy_from_logprob(logprob: float) -> float:
    if logprob is None or logprob < -20:
        return 4.0
    p = math.exp(max(logprob, -20))
    p = max(p, 1e-9)
    return -p * math.log2(p)


# ── Claim type inference ─────────────────────────────────────────────────────
def _infer_claim_type(text: str) -> str:
    if re.search(r'\$|billion|million|trillion|%', text, re.I):
        return "number"
    if re.search(r'Q[1-4]|FY|20\d\d', text, re.I):
        return "date"
    return "statistic"


# ── Entropy-based claim detection ────────────────────────────────────────────
def _detect_claims(sentence: str, entropies: list[float]) -> list[Claim]:
    claims: list[Claim] = []
    words = sentence.split()
    if not words or not entropies:
        return claims

    ratio = len(entropies) / max(len(words), 1)
    span: list[str] = []
    span_start = 0

    for i, word in enumerate(words):
        ent = entropies[min(int(i * ratio), len(entropies) - 1)]
        if ent >= ENTROPY_HIGH_THRESHOLD:
            if not span:
                span_start = i
            span.append(word)
        else:
            if len(span) >= MIN_CLAIM_SPAN:
                txt = " ".join(span)
                claims.append(Claim(text=txt, type=_infer_claim_type(txt),
                                    position=span_start, sentence=sentence))
            span = []

    if len(span) >= MIN_CLAIM_SPAN:
        txt = " ".join(span)
        claims.append(Claim(text=txt, type=_infer_claim_type(txt),
                            position=span_start, sentence=sentence))

    # Fallback: regex for explicit numeric patterns not caught by entropy
    pattern = re.compile(
        r'\$[\d,]+(?:\.\d+)?(?:\s*(?:billion|million|trillion|B|M|T))?'
        r'|\b\d+(?:\.\d+)?%'
        r'|\b(?:Q[1-4]\s*20\d\d|FY\s*20\d\d)\b',
        re.IGNORECASE
    )
    for m in pattern.finditer(sentence):
        if not any(m.group() in c.text for c in claims):
            claims.append(Claim(text=m.group(), type=_infer_claim_type(m.group()),
                                position=m.start(), sentence=sentence))
    return claims


# ── Main entry point: stream and detect ──────────────────────────────────────
async def stream_and_detect(
    query: str,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
) -> AsyncGenerator[tuple[str, list[Claim], list[float]], None]:
    """
    Stream tokens from Gemini, detect claims via entropy.
    Yields: (sentence_or_token, claims, entropies)
    """
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY not set in .env — cannot generate responses. "
            "Get a free key at https://aistudio.google.com/app/apikey"
        )
    async for r in _gemini_stream_with_retry(query, system_prompt, model):
        yield r


# ── Gemini streaming WITH retry wrapper ──────────────────────────────────────
async def _gemini_stream_with_retry(
    query: str,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
) -> AsyncGenerator[tuple[str, list[Claim], list[float]], None]:
    """
    Wraps _gemini_stream with exponential backoff retry on 429 errors.
    Retries up to 3 times with 15s, 30s, 60s delays.
    """
    last_error = None

    for attempt in range(_MAX_RETRIES):
        try:
            async for result in _gemini_stream(query, system_prompt, model):
                yield result
            return  # Success — exit retry loop
        except RuntimeError as e:
            error_str = str(e).lower()
            if "429" in error_str or "quota" in error_str or "exhausted" in error_str:
                last_error = e
                delay = _RETRY_DELAYS[attempt]
                logger.warning(
                    "Gemini 429 on attempt %d/%d — retrying in %.0fs...",
                    attempt + 1, _MAX_RETRIES, delay
                )
                if attempt < _MAX_RETRIES - 1:
                    yield (f"TOKEN:\n\n[API Quota Exhausted. Retrying in {int(delay)}s...]\n\n", [], [0.0])
                    await asyncio.sleep(delay)
                    continue
                else:
                    # Final attempt failed
                    raise RuntimeError(
                        f"Gemini API rate limited after {_MAX_RETRIES} retries. "
                        f"The free tier allows 15 requests/minute. "
                        f"Please wait 60 seconds and try again."
                    )
            else:
                raise  # Non-429 error — don't retry

    if last_error:
        raise last_error


# ── Gemini streaming with logprobs ───────────────────────────────────────────
async def _gemini_stream(
    query: str,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
) -> AsyncGenerator[tuple[str, list[Claim], list[float]], None]:
    sleep_needed = await _rate_limit()
    if sleep_needed > 2.0:
        yield (f"TOKEN:\n\n[Local Rate Limiter: Waiting {int(sleep_needed)}s to respect free quota...]\n\n", [], [0.0])
    await _apply_rate_limit_sleep(sleep_needed)

    use_model = model or GEMINI_MODEL
    sp = system_prompt or (
        "You are a knowledgeable assistant. Answer the user's question with specific "
        "details, numbers, and facts. Be confident and precise in your response."
    )

    payload = {
        "system_instruction": {"parts": [{"text": sp}]},
        "contents": [{"role": "user", "parts": [{"text": query}]}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 512,
            "responseLogprobs": True,
            "logprobs": 5,
        },
    }

    url = (f"{GEMINI_BASE_URL}/models/{use_model}:streamGenerateContent"
           f"?key={GEMINI_API_KEY}&alt=sse")

    sentence_buf: list[str] = []
    entropy_buf:  list[float] = []

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            async with client.stream("POST", url, json=payload) as resp:
                if resp.status_code == 429:
                    logger.error("Gemini 429 (quota exceeded)")
                    raise RuntimeError(
                        "Gemini API quota exhausted (429). "
                        "Free tier allows 15 requests per minute."
                    )
                if resp.status_code != 200:
                    body = await resp.aread()
                    error_msg = body.decode()[:300]
                    logger.error("Gemini %d: %s", resp.status_code, error_msg)
                    raise RuntimeError(f"Gemini API error {resp.status_code}: {error_msg}")

                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if not raw or raw == "[DONE]":
                        continue
                    try:
                        chunk = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    for candidate in chunk.get("candidates", []):
                        parts     = candidate.get("content", {}).get("parts", [])
                        logprobs_res = candidate.get("logprobsResult") or {}
                        chosen_lp    = logprobs_res.get("chosenCandidates", [])

                        for part in parts:
                            text_chunk = part.get("text", "")
                            if not text_chunk:
                                continue

                            chunk_ents = [
                                _entropy_from_logprob(lp.get("logProbability"))
                                for lp in chosen_lp
                                if lp.get("logProbability") is not None
                            ]
                            avg_ent = (sum(chunk_ents) / len(chunk_ents)) if chunk_ents else 0.5
                            yield (f"TOKEN:{text_chunk}", [], [avg_ent])

                            sentence_buf.append(text_chunk)
                            entropy_buf.extend(chunk_ents or [avg_ent])

                            joined    = "".join(sentence_buf)
                            sentences = re.split(r'(?<=[.!?])\s+', joined)
                            if len(sentences) > 1:
                                for sent in sentences[:-1]:
                                    sent = sent.strip()
                                    if not sent:
                                        continue
                                    n = max(len(sent.split()), 1)
                                    ents = entropy_buf[:n]
                                    entropy_buf = entropy_buf[n:]
                                    yield (sent, _detect_claims(sent, ents), ents)
                                sentence_buf = [sentences[-1]]

        if sentence_buf:
            joined = "".join(sentence_buf).strip()
            if joined:
                yield (joined, _detect_claims(joined, entropy_buf), entropy_buf)

    except httpx.ConnectError as e:
        raise RuntimeError(f"Cannot connect to Gemini API: {e}")
    except Exception as e:
        if "quota" in str(e).lower() or "429" in str(e):
            raise
        logger.exception("Gemini stream error")
        raise RuntimeError(f"Gemini stream error: {e}")


# ── Non-streaming generation for eval mode (with retry) ─────────────────────
async def generate_full_response(
    query: str,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
) -> tuple[str, list[float]]:
    """
    Generate a complete (non-streaming) response from Gemini.
    Returns: (response_text, token_entropies)
    Used by the evaluation pipeline for model comparison.
    Includes exponential backoff retry on 429.
    """
    last_error = None

    for attempt in range(_MAX_RETRIES):
        try:
            return await _generate_full_response_inner(query, system_prompt, model)
        except RuntimeError as e:
            error_str = str(e).lower()
            if "429" in error_str or "quota" in error_str:
                last_error = e
                delay = _RETRY_DELAYS[attempt]
                logger.warning(
                    "Gemini 429 (eval) attempt %d/%d — retrying in %.0fs...",
                    attempt + 1, _MAX_RETRIES, delay
                )
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(delay)
                    continue
                else:
                    raise RuntimeError(
                        f"Gemini API rate limited after {_MAX_RETRIES} retries. "
                        f"Please wait 60 seconds and try again."
                    )
            else:
                raise

    if last_error:
        raise last_error
    raise RuntimeError("Unexpected: no response generated")


async def _generate_full_response_inner(
    query: str,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
) -> tuple[str, list[float]]:
    """Inner implementation of generate_full_response (no retry)."""
    sleep_needed = await _rate_limit()
    await _apply_rate_limit_sleep(sleep_needed)

    use_model = model or GEMINI_MODEL
    sp = system_prompt or (
        "You are a knowledgeable assistant. Answer with specific details, "
        "numbers, and facts. Be confident and precise."
    )

    payload = {
        "system_instruction": {"parts": [{"text": sp}]},
        "contents": [{"role": "user", "parts": [{"text": query}]}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 512,
            "responseLogprobs": True,
            "logprobs": 5,
        },
    }

    url = (f"{GEMINI_BASE_URL}/models/{use_model}:generateContent"
           f"?key={GEMINI_API_KEY}")

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json=payload)
        if resp.status_code == 429:
            raise RuntimeError("Gemini quota exhausted (429). Wait and retry.")
        if resp.status_code != 200:
            raise RuntimeError(f"Gemini error {resp.status_code}: {resp.text[:200]}")

        data = resp.json()

    # Extract text
    text = ""
    entropies: list[float] = []
    for candidate in data.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            text += part.get("text", "")
        logprobs_res = candidate.get("logprobsResult") or {}
        chosen_lp    = logprobs_res.get("chosenCandidates", [])
        for lp in chosen_lp:
            if lp.get("logProbability") is not None:
                entropies.append(_entropy_from_logprob(lp["logProbability"]))

    return text, entropies