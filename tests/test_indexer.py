from aria.memory.indexer import WorkspaceIndexer


class FakeVectorStore:
    def __init__(self):
        self.deleted = []
        self.added = []

    def delete_by_path(self, file_path: str):
        self.deleted.append(file_path)

    def add_chunks(self, texts, metadatas, ids=None):
        self.added.append((texts, metadatas, ids))


def test_indexer_skips_secret_files(tmp_path):
    (tmp_path / ".env").write_text("SECRET=do-not-index", encoding="utf-8")
    (tmp_path / "README.md").write_text("hello project", encoding="utf-8")

    store = FakeVectorStore()
    indexer = WorkspaceIndexer(store, str(tmp_path), manifest_path=tmp_path / "manifest.json")
    indexer.run()

    indexed_paths = [metadata["path"] for _, metadatas, _ in store.added for metadata in metadatas]
    assert "README.md" in indexed_paths
    assert ".env" not in indexed_paths


def test_indexer_is_incremental(tmp_path):
    source = tmp_path / "notes.md"
    source.write_text("version one", encoding="utf-8")

    store = FakeVectorStore()
    indexer = WorkspaceIndexer(store, str(tmp_path), manifest_path=tmp_path / "manifest.json")
    indexer.run()
    first_count = len(store.added)

    indexer.run()

    assert first_count == 1
    assert len(store.added) == 1
