from __future__ import annotations

from pathlib import Path


class EmbeddingService:
    """sentence-transformers 封装，懒加载模型，缓存在项目目录下。"""

    MODEL_NAME = "BAAI/bge-small-zh-v1.5"
    CACHE_DIR = str(Path(__file__).resolve().parents[2] / "models")

    def __init__(self):
        self._model = None

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.MODEL_NAME, cache_folder=self.CACHE_DIR)

    def encode(self, texts: list[str]) -> list[list[float]]:
        self._load()
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return vectors.tolist()

    def encode_single(self, text: str) -> list[float]:
        return self.encode([text])[0]

    @staticmethod
    def cosine_similarity(a: list[float], b: list[float]) -> float:
        import numpy as np
        va = np.array(a)
        vb = np.array(b)
        dot = float(np.dot(va, vb))
        norm = float(np.linalg.norm(va) * np.linalg.norm(vb))
        if norm == 0:
            return 0.0
        return dot / norm
