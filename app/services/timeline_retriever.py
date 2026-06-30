from __future__ import annotations

from collections import Counter

from rank_bm25 import BM25Okapi

from app.services.embedding_service import EmbeddingService
from app.services.llm_service import LLMService


def _bigram_tokenize(text: str) -> list[str]:
    """字符级 bigram 切分，适合中文且不依赖外部分词。"""
    text = text.strip()
    if len(text) < 2:
        return list(text)
    return [text[i:i+2] for i in range(len(text) - 1)]


class TimelineRetriever:
    """BM25 + 向量 + 实体匹配 三路召回，RRF 融合排序。"""

    def __init__(
        self,
        embedding_service: EmbeddingService,
        llm_service: LLMService | None = None,
    ):
        self.embedding_service = embedding_service
        self.llm_service = llm_service

    def expand_query(self, user_query: str, recent_text: str) -> str:
        if not self.llm_service or len(user_query) > 30:
            return user_query

        prompt = f"""你是一个小说检索助手。用户输入了续写指令："{user_query}"。
根据小说最近的结尾内容，接下来的剧情最可能需要回调哪些历史设定、人物或未解之谜？
请给出 3-5 个关键词，用空格分隔，不要解释。

【近期内容结尾】
{recent_text[-500:] if len(recent_text) > 500 else recent_text}"""

        try:
            keywords = self.llm_service.generate_sync(
                [{"role": "user", "content": prompt}], max_tokens=50
            )
            return user_query + " " + keywords.strip()
        except Exception:
            return user_query

    def retrieve(
        self,
        timeline: list[dict],
        query: str,
        top_k: int = 5,
        rrf_k: int = 60,
        entity_index: dict[str, list[int]] | None = None,
    ) -> list[dict]:
        """从 timeline 中召回与 query 最相关的 top_k 条，按 chapter_index 升序返回。"""
        if not timeline or not query.strip():
            return timeline[-top_k:] if timeline else []

        contents = [entry["content"] for entry in timeline]
        n = len(contents)

        bm25_ranks = self._bm25_rank(contents, query)
        vec_ranks = self._vector_rank(timeline, query)

        # 实体匹配排名（第三路）
        if entity_index:
            ent_ranks = self._entity_rank(timeline, query, entity_index)
        else:
            ent_ranks = [n] * n  # 无实体索引时给最差排名，不影响前两路

        rrf_scores: list[float] = []
        for i in range(n):
            score = (
                1.0 / (rrf_k + bm25_ranks[i])
                + 1.0 / (rrf_k + vec_ranks[i])
                + 1.0 / (rrf_k + ent_ranks[i])
            )
            rrf_scores.append(score)

        scored = sorted(enumerate(rrf_scores), key=lambda x: x[1], reverse=True)
        top_indices = [idx for idx, _ in scored[:top_k]]

        result = [timeline[i] for i in top_indices]
        result.sort(key=lambda x: x.get("chapter_index", 0))
        return result

    def _bm25_rank(self, contents: list[str], query: str) -> list[int]:
        tokenized = [_bigram_tokenize(c) for c in contents]
        bm25 = BM25Okapi(tokenized)
        scores = bm25.get_scores(_bigram_tokenize(query))
        ranked_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        ranks = [0] * len(scores)
        for rank, idx in enumerate(ranked_indices):
            ranks[idx] = rank
        return ranks

    def _vector_rank(self, timeline: list[dict], query: str) -> list[int]:
        query_emb = self.embedding_service.encode_single(query)

        similarities = []
        for entry in timeline:
            emb = entry.get("embedding")
            if emb:
                sim = EmbeddingService.cosine_similarity(query_emb, emb)
            else:
                sim = 0.0
            similarities.append(sim)

        ranked_indices = sorted(range(len(similarities)), key=lambda i: similarities[i], reverse=True)
        ranks = [0] * len(similarities)
        for rank, idx in enumerate(ranked_indices):
            ranks[idx] = rank
        return ranks

    def _entity_rank(
        self,
        timeline: list[dict],
        query: str,
        entity_index: dict[str, list[int]],
    ) -> list[int]:
        """根据 query 中包含的实体名匹配 entity_index，按命中实体数量排名。"""
        matched_chapters: Counter[int] = Counter()
        for ent_name, ch_indices in entity_index.items():
            if ent_name in query:
                for ci in ch_indices:
                    matched_chapters[ci] += 1

        n = len(timeline)
        ch_idx_to_pos = {
            entry.get("chapter_index", -1): i for i, entry in enumerate(timeline)
        }

        scores = [0] * n
        for ch_idx, hit_count in matched_chapters.items():
            pos = ch_idx_to_pos.get(ch_idx)
            if pos is not None:
                scores[pos] = hit_count

        ranked_indices = sorted(range(n), key=lambda i: scores[i], reverse=True)
        ranks = [0] * n
        for rank, idx in enumerate(ranked_indices):
            ranks[idx] = rank
        return ranks
