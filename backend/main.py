import json
import time
import uuid
import logging
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from typing import AsyncGenerator

from models import (
    ChatRequest, SSEEvent, StreamToken, SessionStats
)
from vault import vault, load_demo_financial_data
from sentinel import sentinel
from rewriter import rewriter
from interceptor import stream_and_detect

# ── Setup ──────────────────────────────────────────────────────────────────────
load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger(__name__)


# ── Lifespan ───────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize all modules on startup."""
    logger.info("🛡️  Project Veracity — starting up...")

    logger.info("Initializing Ground Truth Vault...")
    vault.initialize()
    if vault.get_count() == 0:
        logger.info("Vault empty — loading demo financial data...")
        load_demo_financial_data(vault)
    logger.info(f"Vault ready | {vault.get_count()} documents loaded")

    logger.info("Loading HaluGate Sentinel NLI model...")
    sentinel.initialize()
    logger.info("Sentinel ready")

    logger.info("✅ All systems go. Hallucination firewall is active.")
    yield
    logger.info("Project Veracity shutting down.")


# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Project Veracity — Hallucination Firewall",
    description=(
        "Real-time LLM hallucination detection and auto-correction. "
        "Intercepts Groq streaming output token-by-token, verifies claims "
        "against a ChromaDB vault, and corrects before the user sees it."
    ),
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── SSE Helper ─────────────────────────────────────────────────────────────────
def sse(event_type: str, data: dict) -> str:
    """Format a server-sent event string."""
    event = SSEEvent(event_type=event_type, data=data)
    return f"data: {json.dumps(event.dict())}\n\n"


# ── Firewall Pipeline Generator ────────────────────────────────────────────────
async def firewall_generator(query: str) -> AsyncGenerator[str, None]:
    """
    The core self-healing pipeline.

    Step-by-step per token from Groq:
      1. Yield raw token immediately → frontend streams it live
      2. On sentence completion → extract claims via regex
      3. Per claim → sentinel.is_fact_seeking() → skip if not factual
      4. If factual → vault.search() → find closest ground truth
      5. → sentinel.classify() → NLI label (entailment/neutral/contradiction)
      6. If contradiction → rewriter.rewrite() → corrected sentence
      7. Yield correction event → frontend highlights in green
      8. Yield stats event after each claim
      9. Yield done event with final session stats
    """
    stats = SessionStats()
    pipeline_start = time.perf_counter()

    try:
        async for raw, claims in stream_and_detect(query):

            # ── Raw token → stream to frontend immediately ──────────────────
            if raw.startswith("TOKEN:"):
                token_text = raw[6:]
                token_id = str(uuid.uuid4())[:8]
                token_event = StreamToken(
                    id=token_id,
                    text=token_text,
                    status="streaming"
                )
                yield sse("token", token_event.dict())
                continue

            # ── Error from interceptor ──────────────────────────────────────
            if raw.startswith("ERROR:"):
                yield sse("error", {"message": raw[6:].strip()})
                return

            # ── Sentence complete → run verification pipeline ───────────────
            sentence = raw

            if not claims:
                # No factual claims in this sentence — pass straight through
                stats.claims_skipped += 1
                continue

            stats.total_claims_detected += len(claims)

            for claim in claims:
                claim_start = time.perf_counter()

                # Step 1 — Is this sentence fact-seeking?
                if not sentinel.is_fact_seeking(claim.sentence):
                    stats.claims_skipped += 1
                    logger.debug(f"Skipped (not factual): '{claim.text}'")
                    continue

                # Step 2 — Search Ground Truth Vault
                vault_result = vault.search(claim.text)
                if vault_result is None:
                    # No match in vault — cannot verify, pass through
                    stats.claims_verified += 1
                    logger.debug(f"No vault match for: '{claim.text}'")
                    continue

                # Step 3 — NLI Classification
                nli_result = sentinel.classify(
                    claim_text=claim.text,
                    context_text=vault_result.matched_text
                )

                claim_latency_ms = (time.perf_counter() - claim_start) * 1000

                logger.info(
                    f"Claim: '{claim.text}' | "
                    f"Label: {nli_result.label} | "
                    f"Confidence: {nli_result.confidence:.2f} | "
                    f"Latency: {claim_latency_ms:.1f}ms"
                )

                # Update rolling average latency
                n = stats.claims_verified + 1
                stats.avg_verification_latency_ms = (
                    (stats.avg_verification_latency_ms * (n - 1) + claim_latency_ms) / n
                )
                stats.claims_verified += 1

                # Step 4 — Hallucination detected → rewrite
                if nli_result.is_hallucination:
                    stats.hallucinations_found += 1

                    corrected = rewriter.rewrite(
                        original_sentence=claim.sentence,
                        vault_result=vault_result,
                        nli_result=nli_result
                    )

                    correction_payload = rewriter.build_correction_payload(
                        original=claim.sentence,
                        corrected=corrected,
                        source=vault_result.source_document
                    )

                    stats.corrections_made += 1

                    logger.info(
                        f"HALLUCINATION → CORRECTED | "
                        f"Claim: '{claim.text}' | "
                        f"Source: '{vault_result.source_document}'"
                    )

                    # Yield correction event — frontend highlights in green
                    yield sse("correction", {
                        "original_claim":    claim.text,
                        "original_sentence": claim.sentence,
                        "corrected_sentence": corrected,
                        "source":            vault_result.source_document,
                        "similarity_score":  vault_result.similarity_score,
                        "nli_label":         nli_result.label,
                        "nli_confidence":    nli_result.confidence,
                        "diff_ratio":        correction_payload.get("diff_ratio", 0),
                    })

                # Yield live stats after every verified claim
                yield sse("stats", stats.dict())

        # ── Stream ended → final stats ─────────────────────────────────────
        stats.total_pipeline_latency_ms = (
            (time.perf_counter() - pipeline_start) * 1000
        )

        logger.info(
            f"✅ Pipeline done | "
            f"Claims: {stats.total_claims_detected} | "
            f"Corrections: {stats.corrections_made} | "
            f"Total: {stats.total_pipeline_latency_ms:.1f}ms"
        )

        yield sse("done", stats.dict())

    except Exception as e:
        logger.error(f"Firewall pipeline error: {e}", exc_info=True)
        yield sse("error", {"message": f"Pipeline error: {str(e)}"})


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.post("/chat")
async def chat(request: ChatRequest):
    """
    Main endpoint — accepts a user query, returns SSE stream.

    SSE event types emitted:
      token      → { id, text, status }
      correction → { original_claim, corrected_sentence, source, nli_label, ... }
      stats      → { total_claims_detected, corrections_made, ... }
      done       → { final session stats }
      error      → { message }
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    logger.info(f"Query received: '{request.query[:80]}'")

    return StreamingResponse(
        firewall_generator(request.query),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "Connection":       "keep-alive",
            "X-Accel-Buffering": "no",   # disables nginx buffering
        }
    )


@app.get("/health")
async def health():
    """Health check — confirms all systems are initialized."""
    return {
        "status":           "ok",
        "llm_provider":     "Groq",
        "llm_model":        "llama3-8b-8192",
        "vault_documents":  vault.get_count(),
        "sentinel_loaded":  sentinel._initialized,
        "mock_mode":        os.getenv("USE_MOCK", "false"),
        "version":          "1.0.0"
    }


@app.get("/vault/count")
async def vault_count():
    """Return how many documents are in the Ground Truth Vault."""
    return {"count": vault.get_count()}


@app.post("/vault/add")
async def vault_add(payload: dict):
    """
    Manually add a verified fact to the vault.
    Body: { "text": "Apple revenue was $394.3B in FY2022", "source": "apple_report.pdf" }
    """
    text   = payload.get("text",   "").strip()
    source = payload.get("source", "manual_entry")

    if not text:
        raise HTTPException(status_code=400, detail="text field is required")

    vault.add_document(text=text, source_name=source)
    logger.info(f"Vault add: '{text[:60]}' | source: '{source}'")

    return {"status": "added", "vault_total": vault.get_count()}


@app.delete("/vault/clear")
async def vault_clear():
    """Clear all documents from the vault and reload demo data."""
    vault.clear_vault()
    load_demo_financial_data(vault)
    return {"status": "reset", "vault_total": vault.get_count()}


# ── Run directly ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )