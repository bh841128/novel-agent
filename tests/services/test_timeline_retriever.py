from unittest.mock import MagicMock

from app.services.timeline_retriever import TimelineRetriever, _bigram_tokenize


def test_bigram_tokenize():
    assert _bigram_tokenize("你好世界") == ["你好", "好世", "世界"]
    assert _bigram_tokenize("A") == ["A"]
    assert _bigram_tokenize("") == []


def _make_timeline():
    return [
        {"chapter_index": 0, "chapter": "第1章", "content": "事件：林岚与顾晚重逢\n地点：云岭关废墟", "embedding": [1.0, 0.0, 0.0]},
        {"chapter_index": 1, "chapter": "第2章", "content": "事件：残月会突袭营地\n地点：苍梧城北门", "embedding": [0.0, 1.0, 0.0]},
        {"chapter_index": 2, "chapter": "第3章", "content": "事件：溪水大战\n地点：南方溪谷", "embedding": [0.0, 0.0, 1.0]},
    ]


def test_retrieve_returns_relevant_entries():
    mock_emb = MagicMock()
    mock_emb.encode_single.return_value = [0.9, 0.1, 0.0]
    retriever = TimelineRetriever(mock_emb)
    result = retriever.retrieve(_make_timeline(), "林岚重逢", top_k=2)
    assert len(result) == 2


def test_retrieve_ordered_by_chapter_asc():
    mock_emb = MagicMock()
    mock_emb.encode_single.return_value = [0.5, 0.5, 0.5]
    retriever = TimelineRetriever(mock_emb)
    result = retriever.retrieve(_make_timeline(), "事件", top_k=3)
    indices = [r["chapter_index"] for r in result]
    assert indices == sorted(indices)


def test_retrieve_empty_timeline():
    mock_emb = MagicMock()
    retriever = TimelineRetriever(mock_emb)
    result = retriever.retrieve([], "query")
    assert result == []


def test_retrieve_empty_query():
    mock_emb = MagicMock()
    retriever = TimelineRetriever(mock_emb)
    result = retriever.retrieve(_make_timeline(), "", top_k=2)
    assert len(result) == 2


def test_retrieve_handles_missing_embedding():
    mock_emb = MagicMock()
    mock_emb.encode_single.return_value = [1.0, 0.0, 0.0]
    retriever = TimelineRetriever(mock_emb)
    timeline = [
        {"chapter_index": 0, "chapter": "第1章", "content": "事件：战斗", "embedding": []},
        {"chapter_index": 1, "chapter": "第2章", "content": "事件：重逢林岚", "embedding": [0.9, 0.1, 0.0]},
    ]
    result = retriever.retrieve(timeline, "林岚", top_k=2)
    assert len(result) == 2
