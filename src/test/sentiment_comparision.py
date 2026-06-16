import pandas as pd
from sqlalchemy import create_engine, text

# ==========================================
# 1. DB 설정
# ==========================================
DB_USER = "postgres"      
DB_PASSWORD = "0000"  
DB_HOST = "localhost"          
DB_PORT = "15432"               
DB_NAME = "app"       

def blind_test_random():
    engine = create_engine(f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
    
    print("\n======== 🎲 [전체 데이터 대상] 무작위 블라인드 테스트 ========")
    print("   👉 키워드 필터링 없음. AI의 순수 문맥 이해력 테스트")
    print("   👉 사용자님이 직접 판사(Judge)가 되어주세요.\n")

    with engine.connect() as conn:
        # 각 라벨별로 무작위 10개씩 추출 (총 30개)
        # 쏠림 없이 골고루 확인하기 위함
        dfs = []
        for label in ['positive', 'negative', 'neutral']:
            query = text(f"""
                SELECT title, COALESCE(description, '') as desc_text, sentiment_score 
                FROM community_data 
                WHERE sentiment_label = '{label}'
                ORDER BY RANDOM() 
                LIMIT 10
            """)
            df = pd.read_sql(query, conn)
            df['label'] = label
            dfs.append(df)
        
        # 결과 출력
        for df in dfs:
            current_label = df.iloc[0]['label'].upper()
            print(f"\n[{current_label}]라고 예측한 글 (Random 10 samples)")
            print("-" * 60)
            
            for i, row in df.iterrows():
                full_text = f"{row['title']} {row['desc_text']}".strip()
                # 너무 길면 자르기
                display_text = full_text[:80].replace("\n", " ") + "..." if len(full_text) > 80 else full_text
                score = row['sentiment_score']
                
                print(f"{i+1}. ({score:.2f}) {display_text}")
            
            print("-" * 60)

if __name__ == "__main__":
    blind_test_random()