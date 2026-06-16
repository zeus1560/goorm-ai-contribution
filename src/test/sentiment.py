import pandas as pd
from sqlalchemy import create_engine
import sys

# ==========================================
# 1. DB 연결 설정 (사용자 환경에 맞게 수정)
# ==========================================
DB_USER = "postgres"      # 예: postgres
DB_PASSWORD = "0000"  # 예: 1234
DB_HOST = "localhost"          # 예: localhost
DB_PORT = "15432"               # 예: 5432
DB_NAME = "app"       # 예: crypto_db

# PostgreSQL 연결 엔진 생성
try:
    engine = create_engine(f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
    connection = engine.connect()
    print("✅ DB 연결 성공!")
except Exception as e:
    print(f"❌ DB 연결 실패: {e}")
    sys.exit(1)

def check_news_data():
    table_name = "news_data"
    
    print(f"\n======== [{table_name}] 테이블 데이터 진단 리포트 ========")

    # 1. 전체 데이터 개수 확인
    query_count = f"SELECT COUNT(*) FROM {table_name};"
    total_count = pd.read_sql(query_count, connection).iloc[0, 0]
    print(f"1. 전체 데이터 수: {total_count:,} 개")

    if total_count == 0:
        print("   ⚠️ 데이터가 없습니다. 확인을 종료합니다.")
        return

    # 2. 결측치(NULL) 점검 (특히 content가 비어있으면 분석 불가)
    # 실제 컬럼명에 맞춰 수정 필요 (여기서는 content, sentiment, source로 가정)
    print("\n2. 결측치(NULL) 점검:")
    null_check_query = f"""
    SELECT 
        COUNT(*) FILTER (WHERE title IS NULL) as title_null,
        COUNT(*) FILTER (WHERE description IS NULL OR description = '') as description_null,
        COUNT(*) FILTER (WHERE sentiment_label IS NULL) as sentiment_label_null
    FROM {table_name};
    """
    try:
        null_df = pd.read_sql(null_check_query, connection)
        print(null_df.to_string(index=False))
        
        description_null_count = null_df['description_null'][0]
        if description_null_count > 0:
            print(f"   ⚠️ 경고: 본문(content)이 비어있는 데이터가 {description_null_count}개 있습니다.")
            print("   -> 감성 분석 시 에러가 발생하므로 제외하거나 다시 수집해야 합니다.")
    except Exception as e:
        print(f"   (컬럼명 불일치로 확인 실패: {e})")

    # 3. 출처(Source)별 분포 확인 (뉴스 vs 커뮤니티 비율 파악용)
    # FinBERT와 CryptoBERT를 나누기 위해 가장 중요한 정보입니다.
    print("\n3. 출처(Source)별 데이터 분포:")
    try:
        source_query = f"""
        SELECT sentiment_label, COUNT(*) as count, 
               ROUND(COUNT(*) * 100.0 / {total_count}, 2) as ratio
        FROM {table_name}
        GROUP BY sentiment_label
        ORDER BY count DESC;
        """
        source_df = pd.read_sql(source_query, connection)
        print(source_df)
        print("\n   -> 💡 Tip: 위 리스트를 보고 어떤 source가 '뉴스'이고 '커뮤니티'인지 구분해야 합니다.")
    except Exception as e:
        print(f"   (source 컬럼이 없거나 이름이 다릅니다: {e})")

    # 4. 기존 감성 분석 결과(Sentiment) 분포 확인 (편향 확인)
    print("\n4. 기존 감성 점수(Sentiment) 분포:")
    try:
        # sentiment 혹은 sentiment_score 컬럼이 있다고 가정
        sentiment_query = f"""
        SELECT sentiment, COUNT(*) as count
        FROM {table_name}
        GROUP BY sentiment
        ORDER BY count DESC;
        """
        sentiment_df = pd.read_sql(sentiment_query, connection)
        print(sentiment_df)
        
        # 특정 감정(예: Neutral)이 압도적으로 많은지 확인
        if not sentiment_df.empty:
            top_sentiment = sentiment_df.iloc[0]['sentiment']
            top_ratio = sentiment_df.iloc[0]['count'] / total_count
            if top_ratio > 0.8: # 80% 이상이 한 가지 감정이면
                print(f"   ⚠️ 경고: '{top_sentiment}' 결과가 80% 이상입니다. 이전 모델이 제대로 작동하지 않았을 수 있습니다.")
    except Exception as e:
        print("   (sentiment 컬럼을 찾을 수 없습니다. 아직 분석 전일 수 있습니다.)")

# 실행
check_news_data()
connection.close()