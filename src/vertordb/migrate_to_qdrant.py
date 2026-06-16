import psycopg2
import torch
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct
from sentence_transformers import SentenceTransformer

# 1. 초기 설정 (디바이스 및 모델)
device = "mps" if torch.backends.mps.is_available() else "cpu"
model = SentenceTransformer('intfloat/multilingual-e5-small', device=device)
client = QdrantClient(url="http://localhost:6333")

# 2. PostgreSQL 연결 설정
def get_pg_connection():
    return psycopg2.connect(
        host="localhost",
        port="15432",
        database="app",
        user="postgres",
        password="0000"
    )

# 3. 데이터 이관 핵심 함수 (수정됨)
def migrate_table(table_name, id_column, collection_name):
    print(f"🚀 {table_name} 데이터 이관 시작...")
    conn = get_pg_connection()
    cur = conn.cursor()
    
    # [수정] symbol 컬럼 추가 추출
    query = f"SELECT {id_column}, description, category_id, sentiment_score, symbol FROM {table_name}"
    cur.execute(query)
    rows = cur.fetchall()
    
    points = []
    for row in rows:
        # s_score는 DB의 sentiment_score입니다.
        p_id, content, cat_id, s_score, symbol = row
        
        if not content: continue 

        # 임베딩 생성
        vector = model.encode(f"passage: {content}").tolist()
        
        # [수정] 수집기(Collector)와 완벽히 통일된 페이로드 구조
        points.append(PointStruct(
            id=p_id, 
            vector=vector,
            payload={
                "category_id": cat_id,
                "sentiment": float(s_score) if s_score else 0.0, # 명칭 통일: sentiment
                "source_type": "news" if "news" in table_name else "community",
                "symbol": symbol
            }
        ))
        
        # 100개 단위 일괄 삽입
        if len(points) >= 100:
            client.upsert(collection_name=collection_name, points=points)
            points = []
            print(f" - {table_name}: {p_id}번까지 저장 완료")

    if points:
        client.upsert(collection_name=collection_name, points=points)
    
    cur.close()
    conn.close()
    print(f"✅ {table_name} 이관 완료!\n")

if __name__ == "__main__":
    # 컬렉션별로 각각 이관 실행
    migrate_table("news_data", "news_id", "news_collection")
    migrate_table("community_data", "community_id", "community_collection")