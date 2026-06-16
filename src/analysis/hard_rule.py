import pandas as pd
from sqlalchemy import create_engine, text
import sys

# ==========================================
# 1. DB 설정
# ==========================================
DB_USER = "postgres"      
DB_PASSWORD = "0000"  
DB_HOST = "localhost"          
DB_PORT = "15432"               
DB_NAME = "app"       

def apply_hard_rules():
    print(f"\n======== 🔨 [하드 룰] AI 판정 덮어쓰기 (강제 확정) ========")
    
    engine = create_engine(f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}")

    # 1. [악재 확정] 이 단어 있으면 무조건 Negative (-0.99점)
    # "기분 째진다"가 있든 말든 떡락이면 악재임.
    negative_keywords = [
        "떡락", "나락", "폭락", "한강", "돔황챠", "돔황차", "손절", 
        "설거지", "흑우", "물렸", "상폐", "스캠", "망했", "무섭다", "공포",
        "drained", "Drained", "hacked", "Hacked", "털렸다", "해킹", 
        "숏", "short position"
    ]
    
    # 2. [호재 확정] 이 단어 있으면 무조건 Positive (+0.99점)
    positive_keywords = [
        "떡상", "불장", "투더문", "가즈아", "존버", "졸업", "익절", 
        "반등", "풀매수", "long position" 
        # 주의: '롱'은 '롱 청산' 같은 단어 때문에 제외 (AI에게 맡김)
    ]

    with engine.begin() as conn:
        # A. 악재 처리
        print("1️⃣ 악재 키워드 강제 적용 중...", end="")
        for kw in negative_keywords:
            query = text(f"""
                UPDATE community_data
                SET sentiment_label = 'negative',
                    sentiment_score = 0.99
                WHERE (title LIKE :kw OR description LIKE :kw)
                -- 이미 잘 맞춘 건 건드리지 않음 (선택 사항)
                AND sentiment_label != 'negative'
            """)
            conn.execute(query, {"kw": f"%{kw}%"})
        print(" 완료!")

        # B. 호재 처리
        print("2️⃣ 호재 키워드 강제 적용 중...", end="")
        for kw in positive_keywords:
            query = text(f"""
                UPDATE community_data
                SET sentiment_label = 'positive',
                    sentiment_score = 0.99
                WHERE (title LIKE :kw OR description LIKE :kw)
                AND sentiment_label != 'positive'
            """)
            conn.execute(query, {"kw": f"%{kw}%"})
        print(" 완료!")
        
    print("\n🎉 모든 처리가 끝났습니다. 이제 검증을 해보세요.")
    
    # 즉석 검증
    verify_query(engine)

def verify_query(engine):
    print("\n📊 [최종 결과] 핵심 키워드 재확인")
    keywords = ["떡락", "Drained", "무섭다", "가즈아"]
    
    with engine.connect() as conn:
        for kw in keywords:
            query = text(f"""
                SELECT title, sentiment_label 
                FROM community_data 
                WHERE title LIKE :kw OR description LIKE :kw
                LIMIT 1
            """)
            result = conn.execute(query, {"kw": f"%{kw}%"}).fetchone()
            if result:
                print(f" • '{kw}' -> {result[1].upper()} (제목: {result[0][:15]}...)")
            else:
                print(f" • '{kw}' -> 데이터 없음")

if __name__ == "__main__":
    apply_hard_rules()