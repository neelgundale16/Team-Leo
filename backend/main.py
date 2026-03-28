"""
main.py — Veracity AI: Adaptive Evaluation & Self-Healing Firewall
FastAPI application — orchestrates both single-model firewall mode
and multi-model comparative evaluation mode.
"""

import json, time, uuid, logging, os, asyncio
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from typing import AsyncGenerator, Optional

from models import (
    ChatRequest, SSEEvent, StreamToken, SessionStats, ComparisonResult
)
from vault import vault, load_demo_financial_data
from sentinel import sentinel
from rewriter import rewriter
from interceptor import stream_and_detect
from evaluator import build_model_eval, llm_judge_comparison, DIMENSION_WEIGHTS

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger(__name__)


# ── Lifespan ───────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🛡️  Veracity AI — starting up...")
    vault.initialize()
    if vault.get_count() == 0:
        load_demo_financial_data(vault)
    logger.info(f"Vault ready | {vault.get_count()} documents")
    sentinel.initialize()
    logger.info("Sentinel ready")
    logger.info("✅ All systems go.")
    yield
    logger.info("Shutting down.")


# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Veracity AI — Adaptive Evaluation & Self-Healing Firewall",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


# ── SSE helper ─────────────────────────────────────────────────────────────────
def sse(event_type: str, data: dict, model_id: str = "") -> str:
    payload = {"event_type": event_type, "data": data}
    if model_id:
        payload["model_id"] = model_id
    return f"data: {json.dumps(payload)}\n\n"


# ── Single-model firewall pipeline ────────────────────────────────────────────
async def firewall_pipeline(
    query: str,
    model_id: str
) -> tuple[str, list, int, int, int, float]:
    """
    Runs the full firewall pipeline for ONE model.
    Returns: (full_response, token_entropies, corrections, total_claims, vault_matches, latency_ms)
    Non-streaming — used inside eval mode.
    """
    t0              = time.perf_counter()
    full_response   = ""
    token_entropies = []
    corrections     = 0
    total_claims    = 0
    vault_matches   = 0
    corrected_resp  = None

    async for raw, claims in stream_and_detect(query, model_id):
        if raw.startswith("TOKEN:"):
            parts = raw[6:].split("|")
            text  = parts[0]
            ent   = float(parts[1]) if len(parts) > 1 else 0.0
            full_response   += text
            token_entropies .append(ent)
            continue

        if raw.startswith("ERROR:"):
            break

        if not claims:
            continue

        total_claims += len(claims)
        for claim in claims:
            if not sentinel.is_fact_seeking(claim.sentence):
                continue
            vr = vault.search(claim.text)
            if not vr:
                continue
            vault_matches += 1
            nli = sentinel.classify(claim.text, vr.matched_text)
            if nli.is_hallucination:
                corrections   += 1
                corrected_resp = rewriter.rewrite(claim.sentence, vr, nli)

    latency = (time.perf_counter() - t0) * 1000
    return full_response, token_entropies, corrections, total_claims, vault_matches, latency


# ── Streaming firewall generator (single model, real-time) ────────────────────
async def streaming_firewall(
    query: str, model_id: str
) -> AsyncGenerator[str, None]:
    """
    Real-time streaming firewall for single-model mode.
    Yields SSE events token by token.
    """
    stats = SessionStats(model_id=model_id)
    t0    = time.perf_counter()

    try:
        async for raw, claims in stream_and_detect(query, model_id):

            if raw.startswith("TOKEN:"):
                parts      = raw[6:].split("|")
                token_text = parts[0]
                entropy    = float(parts[1]) if len(parts) > 1 else 0.0
                tid        = str(uuid.uuid4())[:8]

                status = "high_entropy" if entropy > 0.28 else "streaming"
                token_event = StreamToken(
                    id=tid, text=token_text,
                    status=status, entropy=round(entropy, 4)
                )
                yield sse("token", token_event.dict(), model_id)
                continue

            if raw.startswith("ERROR:"):
                yield sse("error", {"message": raw[6:].strip()}, model_id)
                return

            if not claims:
                stats.claims_skipped += 1
                continue

            stats.total_claims_detected += len(claims)

            for claim in claims:
                t1 = time.perf_counter()
                if not sentinel.is_fact_seeking(claim.sentence):
                    stats.claims_skipped += 1
                    continue

                vr = vault.search(claim.text)
                if not vr:
                    stats.claims_verified += 1
                    continue

                nli     = sentinel.classify(claim.text, vr.matched_text)
                latency = (time.perf_counter() - t1) * 1000

                n = stats.claims_verified + 1
                stats.avg_verification_latency_ms = (
                    (stats.avg_verification_latency_ms * (n - 1) + latency) / n
                )
                stats.claims_verified += 1

                if nli.is_hallucination:
                    stats.hallucinations_found += 1
                    corrected = rewriter.rewrite(claim.sentence, vr, nli)
                    payload   = rewriter.build_correction_payload(
                        claim.sentence, corrected, vr.source_document
                    )
                    stats.corrections_made += 1

                    logger.info(
                        f"[{model_id}] CORRECTED | '{claim.text}' → {vr.source_document}"
                    )
                    yield sse("correction", {
                        "original_claim":     claim.text,
                        "original_sentence":  claim.sentence,
                        "corrected_sentence": corrected,
                        "source":             vr.source_document,
                        "similarity_score":   vr.similarity_score,
                        "nli_label":          nli.label,
                        "nli_confidence":     nli.confidence,
                        "diff_ratio":         payload.get("diff_ratio", 0),
                    }, model_id)

                yield sse("stats", stats.dict(), model_id)

        stats.total_pipeline_latency_ms = (time.perf_counter() - t0) * 1000
        yield sse("done", stats.dict(), model_id)

    except Exception as e:
        logger.error(f"Streaming error: {e}", exc_info=True)
        yield sse("error", {"message": str(e)}, model_id)


# ── Eval mode generator (multi-model comparison) ──────────────────────────────
async def eval_generator(
    query: str, models: list
) -> AsyncGenerator[str, None]:
    """
    Multi-model evaluation generator.
    Runs both models in parallel, scores each, judges winner.
    Yields eval_start → eval_progress → eval_complete events.
    """
    session_id = str(uuid.uuid4())[:12]
    yield sse("eval_start", {
        "session_id": session_id,
        "query":      query,
        "models":     models,
    })

    # Run both models concurrently
    model_labels = {
        "gemini-1.5-flash":      "Gemini 1.5 Flash",
        "gemini-2.0-flash-lite": "Gemini 2.0 Flash Lite",
        "gemini-1.5-pro":        "Gemini 1.5 Pro",
        "gemini-2.0-flash":      "Gemini 2.0 Flash",
    }

    tasks = [
        firewall_pipeline(query, m) for m in models
    ]

    yield sse("eval_progress", {"status": "running_models", "models": models})

    try:
        results_raw = await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as e:
        yield sse("error", {"message": f"Eval pipeline failed: {e}"})
        return

    model_results = []
    for i, (model_id, result) in enumerate(zip(models, results_raw)):
        if isinstance(result, Exception):
            logger.error(f"Model {model_id} failed: {result}")
            yield sse("eval_progress", {
                "status":   "model_failed",
                "model_id": model_id,
                "error":    str(result)
            })
            continue

        response, entropies, corrections, total_claims, vault_matches, latency = result

        eval_result = build_model_eval(
            model_id            = model_id,
            model_label         = model_labels.get(model_id, model_id),
            response_text       = response,
            token_entropies     = entropies,
            corrections_applied = corrections,
            total_claims        = total_claims,
            vault_matches       = vault_matches,
            corrected_response  = None,
            latency_ms          = latency,
            query               = query,
        )
        model_results.append(eval_result)

        yield sse("eval_progress", {
            "status":        "model_complete",
            "model_id":      model_id,
            "model_label":   eval_result.model_label,
            "overall_score": eval_result.overall_score,
            "dimensions":    {k: v.dict() for k, v in eval_result.dimensions.items()},
            "response":      response[:400],
            "latency_ms":    eval_result.latency_ms,
            "hallucination_rate": eval_result.hallucination_rate,
            "avg_entropy":   eval_result.avg_token_entropy,
        })

    if len(model_results) < 2:
        yield sse("error", {"message": "Not enough models completed evaluation"})
        return

    # LLM-as-judge comparison
    yield sse("eval_progress", {"status": "judging"})

    a, b = model_results[0], model_results[1]
    winner_id, verdict, rationale = await llm_judge_comparison(
        query,
        a.response_text, a.model_id,
        b.response_text, b.model_id,
        a.overall_score, b.overall_score,
    )

    # Per-dimension winners
    dimension_winner = {}
    for dim in ["factuality", "hallucination_rate", "reasoning", "instruction_following"]:
        score_a = a.dimensions[dim].score if dim in a.dimensions else 0
        score_b = b.dimensions[dim].score if dim in b.dimensions else 0
        dimension_winner[dim] = a.model_id if score_a >= score_b else b.model_id

    comparison = ComparisonResult(
        query            = query,
        session_id       = session_id,
        models           = model_results,
        winner           = winner_id,
        winner_rationale = rationale,
        dimension_winner = dimension_winner,
    )

    yield sse("eval_complete", {
        "session_id":       session_id,
        "winner":           winner_id,
        "winner_label":     model_labels.get(winner_id, winner_id),
        "verdict":          verdict,
        "rationale":        rationale,
        "dimension_winner": dimension_winner,
        "dimension_weights":DIMENSION_WEIGHTS,
        "models": [
            {
                "model_id":          r.model_id,
                "model_label":       r.model_label,
                "overall_score":     r.overall_score,
                "dimensions":        {k: v.dict() for k, v in r.dimensions.items()},
                "hallucination_rate":r.hallucination_rate,
                "avg_entropy":       r.avg_token_entropy,
                "peak_entropy":      r.peak_entropy,
                "corrections":       r.corrections_applied,
                "latency_ms":        r.latency_ms,
                "tokens_total":      r.tokens_total,
                "response":          r.response_text,
            }
            for r in model_results
        ],
    })


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.post("/chat")
async def chat(request: ChatRequest):
    """
    Firewall mode: single model, real-time SSE stream.
    Or eval mode: multi-model comparison.
    """
    if not request.query.strip():
        raise HTTPException(400, "Query cannot be empty")

    logger.info(
        f"Query: '{request.query[:80]}' | "
        f"eval_mode={request.eval_mode} | "
        f"models={request.models}"
    )

    if request.eval_mode and request.models and len(request.models) >= 2:
        return StreamingResponse(
            eval_generator(request.query, request.models),
            media_type="text/event-stream",
            headers={
                "Cache-Control":             "no-cache",
                "Connection":                "keep-alive",
                "X-Accel-Buffering":         "no",
                "Access-Control-Allow-Origin": "*",
            }
        )

    # Default: single-model streaming firewall
    model_id = request.models[0] if request.models else "gemini-1.5-flash"
    return StreamingResponse(
        streaming_firewall(request.query, model_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control":             "no-cache",
            "Connection":                "keep-alive",
            "X-Accel-Buffering":         "no",
            "Access-Control-Allow-Origin": "*",
        }
    )


@app.post("/vault/upload")
async def vault_upload(
    file: UploadFile = File(...),
    source_name: Optional[str] = Form(None)
):
    filename     = source_name or file.filename or "uploaded_document"
    content_type = file.content_type or ""
    raw_bytes    = await file.read()
    chunks: list = []

    if "pdf" in content_type or filename.lower().endswith(".pdf"):
        try:
            import pypdf, io as _io
            reader = pypdf.PdfReader(_io.BytesIO(raw_bytes))
            for page in reader.pages:
                text = page.extract_text()
                if text and text.strip():
                    words, chunk, chars = text.split(), [], 0
                    for w in words:
                        chunk.append(w); chars += len(w) + 1
                        if chars >= 500:
                            chunks.append(" ".join(chunk))
                            chunk, chars = [], 0
                    if chunk: chunks.append(" ".join(chunk))
        except ImportError:
            raise HTTPException(500, "Run: pip install pypdf")
        except Exception as e:
            raise HTTPException(400, f"PDF parse error: {e}")
    else:
        try:
            text = raw_bytes.decode("utf-8")
            words, chunk, chars = text.split(), [], 0
            for w in words:
                chunk.append(w); chars += len(w) + 1
                if chars >= 500:
                    chunks.append(" ".join(chunk))
                    chunk, chars = [], 0
            if chunk: chunks.append(" ".join(chunk))
        except UnicodeDecodeError:
            raise HTTPException(400, "File must be PDF or UTF-8 text")

    if not chunks:
        raise HTTPException(400, "No text extracted")

    vault.add_documents_bulk(chunks, filename)
    return JSONResponse({
        "status": "success", "filename": filename,
        "chunks_added": len(chunks), "vault_total": vault.get_count()
    })


@app.get("/health")
async def health():
    return {
        "status":          "ok",
        "llm_provider":    "Google Gemini",
        "default_model":   "gemini-1.5-flash",
        "eval_models":     ["gemini-1.5-flash", "gemini-2.0-flash-lite"],
        "vault_documents": vault.get_count(),
        "sentinel_loaded": sentinel._initialized,
        "mock_mode":       os.getenv("USE_MOCK", "false"),
        "version":         "2.0.0"
    }


@app.get("/vault/count")
async def vault_count():
    return {"count": vault.get_count()}


@app.post("/vault/add")
async def vault_add(payload: dict):
    text   = payload.get("text", "").strip()
    source = payload.get("source", "manual_entry")
    if not text:
        raise HTTPException(400, "text required")
    vault.add_document(text=text, source_name=source)
    return {"status": "added", "vault_total": vault.get_count()}


@app.delete("/vault/clear")
async def vault_clear():
    vault.clear_vault()
    load_demo_financial_data(vault)
    return {"status": "reset", "vault_total": vault.get_count()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)