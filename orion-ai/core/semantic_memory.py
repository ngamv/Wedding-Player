from itertools import islice
from threading import Lock


class SemanticMemory:
    """Index dérivé des résultats SQLite, reconstruit à la demande."""

    def __init__(self, path, embedding_function=None):
        import chromadb
        from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

        if embedding_function is None:
            embedding_function = ONNXMiniLM_L6_V2()
            embedding_function.DOWNLOAD_PATH = path / "embedding-model"

        self.client = chromadb.PersistentClient(path=str(path))
        self.collection = self.client.get_or_create_collection(
            "orion_workflow_steps", embedding_function=embedding_function
        )
        self.lock = Lock()

    def search(self, memory, query, limit):
        with self.lock:
            documents = memory.documents()
            while batch := list(islice(documents, 100)):
                ids = [row[0] for row in batch]
                existing = set(self.collection.get(ids=ids, include=[])["ids"])
                missing = [row for row in batch if row[0] not in existing]
                if missing:
                    ids, texts, metadata = zip(*missing)
                    self.collection.upsert(ids=list(ids), documents=list(texts), metadatas=list(metadata))
            count = self.collection.count()
            if not count:
                return []
            response = self.collection.query(
                query_texts=[query], n_results=min(limit, count),
                include=["documents", "metadatas", "distances"],
            )
        return [
            {**meta, "text": text, "distance": distance}
            for text, meta, distance in zip(
                response["documents"][0], response["metadatas"][0], response["distances"][0]
            )
        ]
