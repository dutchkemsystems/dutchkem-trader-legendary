from typing import List, Tuple
from rank_bm25 import BM25Okapi


class BM25Retriever:
    def __init__(self):
        self.corpus: List[str] = []
        self.tokenized_corpus: List[List[str]] = []
        self.bm25: BM25Okapi | None = None

    def add_documents(self, documents: List[str]):
        self.corpus.extend(documents)
        self.tokenized_corpus.extend([doc.lower().split() for doc in documents])
        if len(self.tokenized_corpus) > 0:
            self.bm25 = BM25Okapi(self.tokenized_corpus)

    def search(self, query: str, top_k: int = 3) -> List[Tuple[int, float]]:
        if not self.bm25 or not self.corpus:
            return []
        tokenized_query = query.lower().split()
        scores = self.bm25.get_scores(tokenized_query)
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        return ranked[:top_k]
