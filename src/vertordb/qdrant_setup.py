import torch
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance
from sentence_transformers import SentenceTransformer

# 1. 맥북 GPU(MPS) 가속 설정
# M1/M2/M3 칩이라면 'mps'를 사용하고, 아니면 'cpu'를 사용합니다.
device = "mps" if torch.backends.mps.is_available() else "cpu"
print(f"현재 사용 중인 디바이스: {device}")

# 2. 무료 임베딩 모델 로드 (384차원)
# multilingual-e5-small 모델은 한국어 성능이 좋고 가볍습니다.
model = SentenceTransformer('intfloat/multilingual-e5-small', device=device)

# 3. Qdrant 클라이언트 연결 (도커 컨테이너)
client = QdrantClient(url="http://localhost:6333")

# 4. 컬렉션 생성을 위한 설정값
# multilingual-e5-small 모델의 출력 차원은 384입니다.
vector_size = 384 
collections = ["news_collection", "community_collection"]

def create_initial_collections():
    for name in collections:
        if not client.collection_exists(name):
            client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(
                    size=vector_size, 
                    distance=Distance.COSINE # 유사도 계산 방식
                ),
            )
            print(f"✅ 컬렉션 생성 완료: {name}")
        else:
            print(f"ℹ️ 컬렉션이 이미 존재합니다: {name}")

if __name__ == "__main__":
    create_initial_collections()
    
    # 모델 테스트 (정상 작동 확인)
    test_text = "passage: 비트코인 시장 분석 데이터입니다."
    test_vector = model.encode(test_text)
    print(f"테스트 임베딩 성공! 벡터 차원: {len(test_vector)}")