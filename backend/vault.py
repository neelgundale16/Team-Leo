# vault.py — Ground Truth Vault (ChromaDB Vector Database)
# Team: Leo | Hackathon: XEN-O-THON 2026
# YOUR FILE — Data Engineer Role

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from models import VaultResult
from typing import Optional
import os
import logging

# ─────────────────────────────────────────────
# CONSTANTS — never hardcode these anywhere else
# ─────────────────────────────────────────────
VAULT_PATH          = "./vault_db"
COLLECTION_NAME     = "ground_truth_vault"
EMBEDDING_MODEL     = "all-MiniLM-L6-v2"
N_RESULTS           = 3
SIMILARITY_THRESHOLD = 0.75   # below this = not confident enough, return None

# Setup logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════
# CLASS: GroundTruthVault
# The entire vector database wrapped in one clean class
# ═══════════════════════════════════════════════════════
class GroundTruthVault:

    def __init__(self):
        self.embedder = None
        self.client = None
        self.collection = None
        self._initialized = False


    # ───────────────────────────────────────────────────
    # METHOD 1 — initialize()
    # Call this once at app startup
    # Loads the embedding model + connects to ChromaDB
    # ───────────────────────────────────────────────────
    def initialize(self):
        logger.info("[Vault] Starting initialization...")

        # Load the sentence embedding model
        # This converts text → 384 numbers (embeddings)
        logger.info("[Vault] Loading embedding model...")
        self.embedder = SentenceTransformer(EMBEDDING_MODEL)
        logger.info("[Vault] Embedding model loaded ✓")

        # Connect to ChromaDB (creates vault_db/ folder automatically)
        self.client = chromadb.PersistentClient(path=VAULT_PATH)

        # Get existing collection OR create a fresh one
        # cosine = best distance metric for text similarity
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"}
        )

        self._initialized = True

        count = self.collection.count()
        logger.info(f"[Vault] Initialized ✓ — {count} facts in vault")
        return count


    # ───────────────────────────────────────────────────
    # METHOD 2 — add_document()
    # Adds ONE verified fact into the vault
    # text        = the fact e.g. "Apple revenue was $394.3B"
    # source_name = file it came from e.g. "apple_report.pdf"
    # chunk_id    = optional custom ID, auto-generated if None
    # ───────────────────────────────────────────────────
    def add_document(
        self,
        text: str,
        source_name: str,
        chunk_id: Optional[str] = None
    ):
        # Auto-generate a unique ID if none provided
        # hash(text) % 100000 gives a short unique number
        doc_id = chunk_id or f"{source_name}_{hash(text) % 100000}"

        # Convert text to embedding (list of 384 numbers)
        embedding = self.embedder.encode(text).tolist()

        # Store in ChromaDB
        self.collection.add(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[{"source": source_name}]
        )

        logger.info(f"[Vault] Added → '{doc_id}' from {source_name}")
        return doc_id


    # ───────────────────────────────────────────────────
    # METHOD 3 — add_documents_bulk()
    # Adds MANY facts at once (faster than one by one)
    # texts       = list of fact strings
    # source_name = same PDF for all chunks
    # ───────────────────────────────────────────────────
    def add_documents_bulk(self, texts: list[str], source_name: str):
        # Generate IDs for each chunk
        ids = [f"{source_name}_chunk_{i}" for i in range(len(texts))]

        # Convert ALL texts to embeddings at once (faster)
        embeddings = self.embedder.encode(texts).tolist()

        # Same source for all
        metadatas = [{"source": source_name} for _ in texts]

        # Bulk insert into ChromaDB
        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas
        )

        logger.info(f"[Vault] Bulk added {len(texts)} facts from {source_name} ✓")


    # ───────────────────────────────────────────────────
    # METHOD 4 — search()  ← MOST IMPORTANT METHOD
    # Called mid-stream for every detected claim
    # Returns the best matching fact OR None if not confident
    # Target: must complete in < 100ms
    # ───────────────────────────────────────────────────
    def search(self, claim_text: str) -> Optional[VaultResult]:
        # Safety check
        if not self._initialized:
            logger.error("[Vault] Not initialized! Call initialize() first.")
            return None

        # Can't search empty vault
        if self.collection.count() == 0:
            logger.warning("[Vault] Vault is empty — no facts to search")
            return None

        # Convert claim to embedding
        claim_embedding = self.embedder.encode(claim_text).tolist()

        # Search ChromaDB for closest matching facts
        results = self.collection.query(
            query_embeddings=[claim_embedding],
            n_results=min(N_RESULTS, self.collection.count())
        )

        # Pull out the best (first) result
        best_text     = results["documents"][0][0]
        best_source   = results["metadatas"][0][0]["source"]
        best_distance = results["distances"][0][0]

        # ChromaDB cosine distance: 0 = identical, 2 = opposite
        # Convert to similarity score: 1.0 = perfect match, 0.0 = no match
        similarity = 1.0 - (best_distance / 2.0)

        # If similarity is too low → not confident enough → return None
        if similarity < SIMILARITY_THRESHOLD:
            logger.info(
                f"[Vault] No confident match found "
                f"(similarity={similarity:.3f} < {SIMILARITY_THRESHOLD})"
            )
            return None

        logger.info(
            f"[Vault] Match found! similarity={similarity:.3f} "
            f"source={best_source}"
        )

        # Return structured VaultResult for Sentinel to use
        return VaultResult(
            matched_text=best_text,
            source_document=best_source,
            similarity_score=round(similarity, 4),
            distance=round(best_distance, 4)
        )


    # ───────────────────────────────────────────────────
    # METHOD 5 — get_count()
    # Returns how many facts are stored in vault
    # ───────────────────────────────────────────────────
    def get_count(self) -> int:
        return self.collection.count()


    # ───────────────────────────────────────────────────
    # METHOD 6 — clear_vault()
    # Wipes all facts and starts fresh
    # Use carefully — only for testing/reset
    # ───────────────────────────────────────────────────
    def clear_vault(self):
        self.client.delete_collection(COLLECTION_NAME)
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"}
        )
        logger.info("[Vault] Vault cleared ✓ — fresh start")


# ═══════════════════════════════════════════════════════
# FUNCTION: load_demo_financial_data()
# Seeds the vault with 10 real financial facts
# Called once at startup for the hackathon demo
# ═══════════════════════════════════════════════════════
def load_demo_financial_data(vault: GroundTruthVault):
    logger.info("[Vault] Loading demo financial facts...")

    # Each tuple = (fact text, source PDF name)
    facts = [
        (
            "Apple Inc reported total revenue of $394.3 billion "
            "in fiscal year 2022.",
            "apple_annual_report_2022.pdf"
        ),
        (
            "Microsoft Azure cloud revenue grew by 28% "
            "in Q4 fiscal year 2023.",
            "microsoft_q4_2023_earnings.pdf"
        ),
        (
            "Tesla delivered 1.81 million vehicles globally "
            "in the full year 2023.",
            "tesla_2023_delivery_report.pdf"
        ),
        (
            "The US Federal Reserve held interest rates at "
            "5.25% to 5.50% in December 2023.",
            "fed_reserve_december_2023_statement.pdf"
        ),
        (
            "Amazon Web Services generated $90.8 billion "
            "in revenue for full year 2023.",
            "amazon_aws_annual_report_2023.pdf"
        ),
        (
            "Nvidia reported total revenue of $60.9 billion "
            "for fiscal year 2024.",
            "nvidia_fy2024_annual_report.pdf"
        ),
        (
            "JPMorgan Chase reported net income of $49.6 billion "
            "for the full year 2023.",
            "jpmorgan_2023_annual_report.pdf"
        ),
        (
            "The US Consumer Price Index rose 3.4% "
            "year-over-year in December 2023.",
            "us_bureau_labor_statistics_dec_2023.pdf"
        ),
        (
            "The S&P 500 index closed at 4769.83 "
            "on December 29, 2023.",
            "sp500_market_close_dec2023.pdf"
        ),
        (
            "Goldman Sachs reported net earnings of $8.5 billion "
            "for the full year 2023.",
            "goldman_sachs_2023_annual_report.pdf"
        ),
    ]

    # Add all facts to vault
    for text, source in facts:
        vault.add_document(text=text, source_name=source)

    logger.info(f"[Vault] {len(facts)} demo facts loaded ✓")


# ═══════════════════════════════════════════════════════
# SINGLETON — one vault instance shared across the app
# Every other file does: from vault import vault
# ═══════════════════════════════════════════════════════
vault = GroundTruthVault()