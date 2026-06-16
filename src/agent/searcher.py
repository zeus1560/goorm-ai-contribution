import os
import torch
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from sentence_transformers import SentenceTransformer

class QdrantSearcher:
    def __init__(self):
        # 맥북 가속(MPS) 설정 및 모델 로드
        self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        self.model = SentenceTransformer('intfloat/multilingual-e5-small', device=self.device)
        self.client = QdrantClient(
            url=os.getenv("QDRANT_HOST"),
            api_key=os.getenv("QDRANT_API_KEY")
        )
    # searcher.py 파일의 search_similar_contexts 함수 일부분 수정
    def search_similar_contexts(self, query_text, category_id, limit=3):
        query_vector = self.model.encode(f"query: {query_text}").tolist()
        search_filter = Filter(must=[FieldCondition(key="category_id", match=MatchValue(value=category_id))])
        
        results = []
        for col in ["news_collection", "community_collection"]:
            search_res = self.client.query_points(
                collection_name=col,
                query=query_vector,
                query_filter=search_filter,
                limit=limit
            ).points  # points 리스트 추출
            
            for r in search_res:
                # r.payload를 통해 실제 데이터에 접근해야 합니다.
                results.append({
                    "id": r.id,
                    "source": "news" if "news" in col else "community",
                    "score": r.score
                })
        return sorted(results, key=lambda x: x['score'], reverse=True)[:limit]