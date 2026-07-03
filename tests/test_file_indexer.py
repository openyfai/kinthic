import pytest
from unittest.mock import MagicMock
from silex.memory.file_indexer import FileIndexer
from silex.tools.rag_query import RAGQueryTool

def test_file_indexer_chunk_fixed():
    indexer = FileIndexer.__new__(FileIndexer)
    text = "line1\nline2\nline3\nline4\nline5\nline6\nline7\nline8\nline9\n"
    chunks = list(indexer._chunk_fixed(text, window=20, overlap=5))
    assert len(chunks) > 0
    assert chunks[0]["text"] == text[:20]

def test_file_indexer_chunk_prose():
    indexer = FileIndexer.__new__(FileIndexer)
    text = "# Title\nThis is prose.\n## Section 1\nMore prose here.\n"
    chunks = list(indexer._chunk_prose(text))
    assert len(chunks) == 2
    assert "# Title" in chunks[0]["text"]
    assert "## Section 1" in chunks[1]["text"]

def test_file_indexer_chunk_code():
    indexer = FileIndexer.__new__(FileIndexer)
    text = "def func_one():\n    pass\n\nclass ClassOne:\n    def method():\n        pass\n"
    chunks = list(indexer._chunk_code(text))
    assert len(chunks) == 2
    assert "func_one" in chunks[0]["text"]
    assert "ClassOne" in chunks[1]["text"]

@pytest.mark.asyncio
async def test_rag_query_tool():
    indexer_mock = MagicMock()
    indexer_mock.search.return_value = [
        {"content": "mock content", "path": "file.py", "start_line": 10, "distance": 0.1}
    ]
    tool = RAGQueryTool(indexer_mock)
    res = await tool.execute(query="test query")
    assert "Found 1 relevant file chunks" in res
    assert "file.py" in res
    assert "mock content" in res
    indexer_mock.search.assert_called_once_with("test query", n_results=5)
