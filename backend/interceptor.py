"""
interceptor.py — Streaming Interceptor with Entropy-Based Claim Detection

Detection strategy: Shannon entropy computed from per-token log probabilities
returned by the Groq API. High-entropy tokens signal epistemic uncertainty in
the model — these are the positions where hallucinations occur.

Entropy per token:
    H(t) = -sum( p_i * log(p_i) ) over top-k candidate tokens at position t

A claim boundary is detected when a token's entropy exceeds ENTROPY_THRESHOLD,
meaning the model was uncertain which token to generate — a strong signal that
the surrounding span is a factual claim being "guessed" rather than recalled.

This replaces hardcoded regex patterns with a fully LLM-driven signal.
Reference: Semantic Entropy (Kuhn et al.), Kernel Language Entropy (ICLR 2024)
"""

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

# ── Groq Config ────────────────────────────────────────────────────────────────
GROQ_API_URL  = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL    = "llama3-8b-8192"
GROQ_TOP_LOGPROBS = 5          # number of candidate tokens per position

# ── Entropy Thresholds ─────────────────────────────────────────────────────────
# Tokens with H > ENTROPY_THRESHOLD are considered uncertain (claim candidates)
# Derived from REVERSE algorithm: tau_generative = 0.003 mapped to entropy scale
ENTROPY_THRESHOLD   = 1.2      # nats — tunable, lower = more sensitive
WINDOW_SIZE         = 6        # sliding window to smooth entropy signal
BURST_MIN_TOKENS    = 2        # minimum consecutive high-entropy tokens = claim span

# ── Sentence Boundary ──────────────────────────────────────────────────────────
import re
SENTENCE_END = re.compile(r'(?<=[.!?])\s+')


# ── Entropy Calculator ─────────────────────────────────────────────────────────
def compute_token_entropy(top_logprobs: list[dict]) -> float:
    """
    Compute Shannon entropy from top-k log probability distribution
    returned by the Groq API for a single token position.

    H = -sum( p_i * log(p_i) )

    Args:
        top_logprobs: list of {"token": str, "logprob": float} dicts
                      from Groq API response

    Returns:
        entropy in nats (float). Higher = model was more uncertain.
    """
    if not top_logprobs:
        return 0.0

    # Convert log probs to probabilities
    log_probs = [entry["logprob"] for entry in top_logprobs]

    # Numerical stability: subtract max before exp
    max_lp    = max(log_probs)
    probs_raw = [math.exp(lp - max_lp) for lp in log_probs]
    total     = sum(probs_raw)
    probs     = [p / total for p in probs_raw]

    # Shannon entropy
    entropy = -sum(p * math.log(p + 1e-12) for p in probs if p > 0)
    return round(entropy, 6)


def smooth_entropy(window: deque) -> float:
    """Return mean entropy over the sliding window."""
    if not window:
        return 0.0
    return sum(window) / len(window)


def detect_claim_from_span(
    span_tokens: list[str],
    span_entropies: list[float],
    sentence: str,
    position: int
) -> Claim | None:
    """
    Given a high-entropy token span, build a Claim object.
    The claim text is the span itself.
    Type is inferred from the span content — not from hardcoded regex
    but from the LLM's own uncertainty pattern.
    """
    claim_text = "".join(span_tokens).strip()
    if not claim_text:
        return None

    avg_entropy = sum(span_entropies) / len(span_entropies)

    # Infer claim type from average entropy magnitude
    # High entropy = numerical/statistical claim (model is guessing a number)
    # Medium entropy = named entity or temporal claim
    # Lower (but above threshold) = general factual claim
    if avg_entropy > 2.5:
        claim_type = "statistic"
    elif avg_entropy > 1.8:
        claim_type = "number"
    elif avg_entropy > 1.5:
        claim_type = "name"
    elif avg_entropy > 1.3:
        claim_type = "date"
    else:
        claim_type = "general"

    return Claim(
        text     = claim_text,
        type     = claim_type,
        position = position,
        sentence = sentence.strip()
    )


def extract_claims_from_entropy(
    tokens:    list[str],
    entropies: list[float],
    sentence:  str
) -> list[Claim]:
    """
    Scan token-level entropy values across a completed sentence.
    Identify contiguous spans of high-entropy tokens as claim boundaries.

    This is the entropy-based replacement for regex pattern matching.
    The model's own uncertainty signal drives detection — no hardcoding.
    """
    if not tokens or not entropies:
        return []

    claims      = []
    in_span     = False
    span_tokens : list[str]   = []
    span_entropies: list[float] = []
    span_start  = 0

    for i, (token, entropy) in enumerate(zip(tokens, entropies)):
        if entropy > ENTROPY_THRESHOLD:
            if not in_span:
                in_span    = True
                span_start = i
                span_tokens    = [token]
                span_entropies = [entropy]
            else:
                span_tokens.append(token)
                span_entropies.append(entropy)
        else:
            if in_span and len(span_tokens) >= BURST_MIN_TOKENS:
                # Span ended — create claim
                claim = detect_claim_from_span(
                    span_tokens, span_entropies, sentence, span_start
                )
                if claim:
                    claims.append(claim)
            in_span        = False
            span_tokens    = []
            span_entropies = []

    # Flush any open span at sentence end
    if in_span and len(span_tokens) >= BURST_MIN_TOKENS:
        claim = detect_claim_from_span(
            span_tokens, span_entropies, sentence, span_start
        )
        if claim:
            claims.append(claim)

    return claims


# ── Groq Stream with Logprobs ──────────────────────────────────────────────────
async def _stream_groq(query: str) -> AsyncGenerator[tuple[str, float], None]:
    """
    Stream tokens from Groq API with per-token log probabilities.
    Yields (token_text, entropy) tuples.

    Groq logprobs spec (OpenAI-compatible):
      response.choices[0].delta.content          → token text
      response.choices[0].logprobs.content[0]    → logprob entry
        .logprob                                  → log P of chosen token
        .top_logprobs                             → list of top-k alternatives

    Get your free API key: https://console.groq.com
    Add to backend/.env: GROQ_API_KEY=gsk_...
    """
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. "
            "Get a free key at console.groq.com and add to backend/.env"
        )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
    }

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {
                "role":    "system",
                "content": (
                    "You are a financial analysis assistant. "
                    "Answer questions about company financials, market data, "
                    "and economic indicators using specific numbers, "
                    "percentages, and statistics."
                )
            },
            {"role": "user", "content": query}
        ],
        "stream":     True,
        "temperature": 0.7,
        "max_tokens":  500,
        "logprobs":    True,
        "top_logprobs": GROQ_TOP_LOGPROBS,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        async with client.stream(
            "POST", GROQ_API_URL,
            headers=headers,
            json=payload
        ) as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:].strip()
                if data == "[DONE]":
                    break

                try:
                    chunk   = json.loads(data)
                    choice  = chunk["choices"][0]
                    content = choice["delta"].get("content", "")
                    if not content:
                        continue

                    # Extract entropy from logprobs if available
                    entropy = 0.0
                    logprobs_data = choice.get("logprobs")
                    if logprobs_data and logprobs_data.get("content"):
                        lp_entry    = logprobs_data["content"][0]
                        top_lp_list = lp_entry.get("top_logprobs", [])
                        if top_lp_list:
                            entropy = compute_token_entropy(top_lp_list)
                        else:
                            # Fallback: single token entropy from its own logprob
                            lp      = lp_entry.get("logprob", 0.0)
                            p       = math.exp(lp)
                            entropy = -(p * math.log(p + 1e-12))

                    yield (content, entropy)

                except (json.JSONDecodeError, KeyError, IndexError):
                    continue


# ── Mock Stream with Synthetic Entropy ────────────────────────────────────────
async def _stream_mock(query: str) -> AsyncGenerator[tuple[str, float], None]:
    """
    Mock stream for testing without a Groq API key.
    Assigns synthetic entropy values — high entropy on hallucinated values
    so the correction pipeline triggers correctly in demo mode.
    Enable: USE_MOCK=true in backend/.env
    """
    # (token, entropy) — high entropy assigned to hallucinated numbers
    mock_tokens: list[tuple[str, float]] = [
        ("Apple", 0.4), (" Inc", 0.3), (" reported", 0.5),
        (" revenue", 0.6), (" of", 0.4),
        (" $", 1.4), ("523", 2.8), (" billion", 2.6),   # HIGH — hallucination
        (" in", 0.3), (" fiscal", 0.5), (" year", 0.4), (" 2022", 0.9),
        (".", 0.1), (" ",  0.1),
        ("Microsoft", 0.4), (" Azure", 0.5), (" cloud", 0.4),
        (" revenue", 0.5), (" grew", 0.6),
        (" 45", 2.9), ("%", 2.7),                        # HIGH — hallucination
        (" year", 0.4), ("-over-", 0.3), ("year", 0.3),
        (" in", 0.3), (" Q4", 0.7), (" 2023", 0.8),
        (".", 0.1), (" ", 0.1),
        ("Tesla", 0.4), (" delivered", 0.5),
        (" 2.1", 2.8), (" million", 2.5),                # HIGH — hallucination
        (" vehicles", 0.4), (" in", 0.3), (" 2023", 0.6),
        (".", 0.1), (" ", 0.1),
        ("The", 0.3), (" Federal", 0.4), (" Reserve", 0.4),
        (" held", 0.5), (" interest", 0.4), (" rates", 0.5), (" at",  0.4),
        (" 4", 2.7), (".", 2.5), ("75", 2.8), ("%", 2.6), # HIGH — hallucination
        (" in", 0.3), (" December", 0.5), (" 2023", 0.6),
        (".", 0.1),
    ]

    for token, entropy in mock_tokens:
        yield (token, entropy)
        await asyncio.sleep(0.04)


# ── Core Interceptor Generator ─────────────────────────────────────────────────
async def stream_and_detect(
    query: str
) -> AsyncGenerator[tuple[str, list[Claim]], None]:
    """
    Main interceptor generator — called by main.py firewall pipeline.

    Per token:
      1. Record (token, entropy) pair
      2. Yield raw token immediately for live frontend streaming
      3. Buffer into sentences
      4. On sentence boundary: run entropy-based claim detection
         across all token entropies in that sentence
      5. Yield (sentence, [Claim, ...])

    Yields:
      ("TOKEN:<text>", [])         raw token — stream to UI immediately
      ("<sentence>",  [Claim, …])  completed sentence + entropy-detected claims
      ("ERROR:<msg>", [])          on failure
    """
    use_mock = os.getenv("USE_MOCK", "false").lower() == "true"

    text_buffer    : str        = ""
    token_buffer   : list[str]  = []
    entropy_buffer : list[float]= []
    entropy_window : deque      = deque(maxlen=WINDOW_SIZE)
    token_count    : int        = 0

    stream_fn = _stream_mock if use_mock else _stream_groq

    try:
        async for token, entropy in stream_fn(query):
            token_count += 1

            # Track entropy signal
            entropy_window.append(entropy)
            text_buffer    += token
            token_buffer   .append(token)
            entropy_buffer .append(entropy)

            # Yield raw token immediately — do not block on verification
            yield (f"TOKEN:{token}", [])

            # Log smoothed entropy for observability
            smoothed = smooth_entropy(entropy_window)
            if smoothed > ENTROPY_THRESHOLD:
                logger.debug(
                    f"High entropy window: {smoothed:.3f} "
                    f"at token '{token.strip()}'"
                )

            # Check for completed sentences
            parts = SENTENCE_END.split(text_buffer)
            if len(parts) > 1:
                for sentence in parts[:-1]:
                    sentence = sentence.strip()
                    if not sentence:
                        continue

                    # Align token/entropy buffers to this sentence
                    sentence_len   = len(sentence)
                    char_count     = 0
                    sentence_tokens   : list[str]   = []
                    sentence_entropies: list[float] = []

                    for tok, ent in zip(token_buffer, entropy_buffer):
                        if char_count >= sentence_len:
                            break
                        sentence_tokens.append(tok)
                        sentence_entropies.append(ent)
                        char_count += len(tok)

                    # Entropy-based claim detection
                    claims = extract_claims_from_entropy(
                        sentence_tokens,
                        sentence_entropies,
                        sentence
                    )

                    logger.debug(
                        f"Sentence: '{sentence[:60]}' | "
                        f"Entropy claims: {len(claims)} | "
                        f"Peak entropy: {max(sentence_entropies, default=0):.3f}"
                    )

                    yield (sentence, claims)

                # Keep trailing incomplete fragment
                text_buffer    = parts[-1]
                # Trim buffers to match remaining text
                remaining_len  = len(text_buffer)
                char_count     = 0
                new_tok_buf : list[str]   = []
                new_ent_buf : list[float] = []
                for tok, ent in zip(
                    reversed(token_buffer),
                    reversed(entropy_buffer)
                ):
                    if char_count >= remaining_len:
                        break
                    new_tok_buf.insert(0, tok)
                    new_ent_buf.insert(0, ent)
                    char_count += len(tok)
                token_buffer   = new_tok_buf
                entropy_buffer = new_ent_buf

        # Flush remaining buffer
        if text_buffer.strip():
            claims = extract_claims_from_entropy(
                token_buffer, entropy_buffer, text_buffer.strip()
            )
            yield (text_buffer.strip(), claims)

    except ValueError as e:
        logger.error(f"Config error: {e}")
        yield (f"ERROR:{str(e)}", [])

    except httpx.HTTPStatusError as e:
        logger.error(f"Groq API error {e.response.status_code}")
        yield (f"ERROR:Groq API returned {e.response.status_code}", [])

    except httpx.ConnectError:
        logger.error("Cannot reach Groq API")
        yield ("ERROR:Cannot reach Groq API. Check internet connection.", [])

    except Exception as e:
        logger.error(f"Interceptor error: {e}", exc_info=True)
        yield (f"ERROR:{str(e)}", [])

    logger.info(
        f"Stream complete | tokens: {token_count} | "
        f"entropy threshold: {ENTROPY_THRESHOLD}"
    )