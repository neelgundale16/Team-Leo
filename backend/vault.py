# vault.py

import logging
from dataclasses import dataclass
from typing import Optional, List

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


@dataclass
class VaultSearchResult:
    matched_text: str
    source_document: str
    similarity_score: float


class GroundTruthVault:
    def __init__(self):
        self._initialized = False
        self._embedder = None
        self._client = None
        self._collection = None
        self._count = 0

    def initialize(self):
        if self._initialized:
            return

        logger.info("[Vault] Starting initialization...")
        logger.info("[Vault] Loading embedding model...")

        self._embedder = SentenceTransformer("all-MiniLM-L6-v2")

        self._client = chromadb.Client(
            Settings(anonymized_telemetry=False)
        )

        self._collection = self._client.get_or_create_collection(
            name="ground_truth_vault",
            metadata={"description": "Verified source chunks for Project Veracity"}
        )

        self._count = self._collection.count()
        self._initialized = True

        logger.info("[Vault] Embedding model loaded ✓")
        logger.info(f"[Vault] Initialized ✓ — {self._count} facts in vault")

    def get_count(self) -> int:
        return self._count if self._initialized else 0

    def add_document(self, text: str, source_name: str = "manual_entry"):
        if not self._initialized:
            self.initialize()

        text = text.strip()
        if not text:
            return

        embedding = self._embedder.encode(text).tolist()
        doc_id = f"{source_name}_{self._count + 1}"

        self._collection.add(
            ids=[doc_id],
            documents=[text],
            embeddings=[embedding],
            metadatas=[{"source": source_name}]
        )

        self._count += 1
        logger.info(f"[Vault] Added 1 chunk from '{source_name}'")

    def add_documents_bulk(self, texts: List[str], source_name: str):
        if not self._initialized:
            self.initialize()

        cleaned = [t.strip() for t in texts if t and t.strip()]
        if not cleaned:
            return

        embeddings = self._embedder.encode(cleaned).tolist()
        start = self._count + 1

        ids = [f"{source_name}_{start + i}" for i in range(len(cleaned))]
        metadatas = [{"source": source_name} for _ in cleaned]

        self._collection.add(
            ids=ids,
            documents=cleaned,
            embeddings=embeddings,
            metadatas=metadatas
        )

        self._count += len(cleaned)
        logger.info(f"[Vault] Added {len(cleaned)} chunks from '{source_name}'")

    def search(self, query: str, top_k: int = 1, min_similarity: float = 0.45) -> Optional[VaultSearchResult]:
        if not self._initialized or self._count == 0:
            return None

        query = query.strip()
        if not query:
            return None

        query_embedding = self._embedder.encode(query).tolist()

        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k
        )

        documents = results.get("documents", [[]])
        metadatas = results.get("metadatas", [[]])
        distances = results.get("distances", [[]])

        if not documents or not documents[0]:
            return None

        matched_text = documents[0][0]
        metadata = metadatas[0][0] if metadatas and metadatas[0] else {}
        distance = distances[0][0] if distances and distances[0] else 1.0

        similarity = max(0.0, 1.0 - float(distance))

        if similarity < min_similarity:
            return None

        return VaultSearchResult(
            matched_text=matched_text,
            source_document=metadata.get("source", "unknown_source"),
            similarity_score=round(similarity, 4)
        )

    def clear_vault(self):
        if not self._initialized:
            self.initialize()

        try:
            self._client.delete_collection("ground_truth_vault")
        except Exception:
            pass

        self._collection = self._client.get_or_create_collection(
            name="ground_truth_vault",
            metadata={"description": "Verified source chunks for Project Veracity"}
        )
        self._count = 0
        logger.info("[Vault] Cleared vault")


vault = GroundTruthVault()


def load_demo_financial_data(vault_instance: GroundTruthVault):
    demo_docs = [
        (
            "Apple FY2022 revenue was $394.33 billion. "
            "iPhone revenue was $205.49 billion. "
            "Services revenue was $78.13 billion.",
            "apple_fy2022_demo.txt"
        ),
        (
            "Microsoft fiscal year 2023 revenue was $211.9 billion. "
            "Operating income was $88.5 billion. "
            "Net income was $72.4 billion.",
            "microsoft_fy2023_demo.txt"
        ),
        (
            "Tesla delivered 1.81 million vehicles in 2023. "
            "Total automotive revenue in 2023 was $82.4 billion.",
            "tesla_2023_demo.txt"
        ),
        (
            "The Federal Reserve target rate in late 2023 was in the range "
            "of 5.25% to 5.50%.",
            "fed_rates_demo.txt"
        ),
    ]

    for text, source in demo_docs:
        vault_instance.add_document(text, source)