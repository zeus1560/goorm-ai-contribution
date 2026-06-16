import pandas as pd
from sqlalchemy import create_engine, text

DB_USER = "postgres"      
DB_PASSWORD = "0000"  
DB_HOST = "localhost"          
DB_PORT = "15432"               
DB_NAME = "app"       

def verify_data_fixed():
    engine = create_engine(f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
    print("\n📊 [재검증] 데이터 품질 확인\n")

    with engine.connect() as conn:
        # 1. 핵심 키워드 재검사
        print("1️⃣ 핵심 키워드 재검사")
        keywords = ["떡락", "Drained", "drained", "무섭다", "공포", "롱", "가즈아"]
        
        for kw in keywords:
            query = text(f"""
                SELECT title, sentiment_label, sentiment_score
                FROM community_data
                WHERE (title LIKE :kw OR description LIKE :kw)
                AND sentiment_label IS NOT NULL  -- NULL 제외
                ORDER BY community_id DESC
                LIMIT 1
            """)
            df = pd.read_sql(query, conn, params={"kw": f"%{kw}%"})
            
            if not df.empty:
                row = df.iloc[0]
                label = row['sentiment_label']
                score = row['sentiment_score']
                
                # 라벨이 None일 경우 방지
                if label:
                    label = label.lower()
                    print(f" • '{kw}': [{label.upper()}] ({score:.4f})")
                else:
                    print(f" • '{kw}': [NULL] (분석 안됨)")
            else:
                print(f" • '{kw}': 데이터 없음")
        
        print("-" * 30)

        # 2. 전체 분포 (에러 수정됨)
        print("2️⃣ 전체 분포")
        # NULL이 아닌 것만 카운트
        dist_query = "SELECT sentiment_label, COUNT(*) as cnt FROM community_data WHERE sentiment_label IS NOT NULL GROUP BY sentiment_label"
        df_dist = pd.read_sql(dist_query, conn)
        
        total = df_dist['cnt'].sum()
        for _, row in df_dist.iterrows():
            if row['sentiment_label']: # None 체크
                ratio = (row['cnt'] / total) * 100
                print(f" • {row['sentiment_label'].upper()}: {row['cnt']} ({ratio:.1f}%)")

if __name__ == "__main__":
    verify_data_fixed()