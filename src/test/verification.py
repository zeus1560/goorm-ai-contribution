import pandas as pd
from sqlalchemy import create_engine, text
from sklearn.metrics import classification_report, confusion_matrix
import numpy as np

# ==========================================
# 1. DB 설정
# ==========================================
DB_USER = "postgres"
DB_PASSWORD = "0000"
DB_HOST = "localhost"
DB_PORT = "15432"
DB_NAME = "app"

# ==========================================
# 2. 정답지 생성기 (키워드 기반 Ground Truth)
# ==========================================
def get_ground_truth(text, data_type='community'):
    text = text.lower()
    
    # [커뮤니티용 정답 키워드]
    if data_type == 'community':
        neg_keywords = ["떡락", "나락", "폭락", "한강", "손절", "설거지", "물렸", "상폐", "스캠", "망했", "공포", "drained", "hacked", "털렸다", "숏", "short"]
        pos_keywords = ["떡상", "불장", "투더문", "가즈아", "졸업", "익절", "반등", "풀매수", "long", "롱"]
    
    # [뉴스용 정답 키워드] (영어/한국어 혼용 대비)
    else:
        neg_keywords = ["plunge", "crash", "drop", "crisis", "hacked", "ban", "lawsuit", "폭락", "급락", "위기", "해킹", "규제", "소송"]
        pos_keywords = ["surge", "jump", "rally", "approval", "etf", "partnership", "급등", "상승", "승인", "파트너십", "호재"]

    # 키워드 검색
    has_neg = any(k in text for k in neg_keywords)
    has_pos = any(k in text for k in pos_keywords)

    # 정답 판정 (키워드가 명확한 것만 테스트 대상)
    if has_neg and not has_pos:
        return 'negative'
    elif has_pos and not has_neg:
        return 'positive'
    else:
        return None  # 판단 보류 (채점 제외)

def calculate_metrics_for_table(table_name, engine):
    print(f"\n======== 🕵️‍♂️ [{table_name.upper()}] 데이터 검증 (Sample 10%) ========")
    
    # 1. 데이터 샘플링 (10% 무작위 추출)
    # TABLESAMPLE은 빠르게 10%를 가져옵니다.
    query = text(f"""
        SELECT title, COALESCE(description, '') as desc_text, sentiment_label 
        FROM {table_name}
        TABLESAMPLE SYSTEM (10) 
        WHERE sentiment_label IS NOT NULL
    """)
    
    try:
        with engine.connect() as conn:
            df = pd.read_sql(query, conn)
    except Exception as e:
        print(f"⚠️ 테이블 조회 실패: {e}")
        return

    if df.empty:
        print("❌ 데이터가 부족합니다.")
        return

    print(f"👉 샘플링된 데이터: {len(df)}개")

    # 2. 정답지(y_true) vs 예측값(y_pred) 생성
    y_true = []
    y_pred = []
    valid_count = 0

    data_type = 'community' if 'community' in table_name else 'news'

    for _, row in df.iterrows():
        full_text = f"{row['title']} {row['desc_text']}"
        
        # 키워드로 '진짜 정답' 유추
        true_label = get_ground_truth(full_text, data_type)
        pred_label = row['sentiment_label'].lower()
        
        # 정답을 알 수 있는 데이터만 검증에 사용
        if true_label:
            y_true.append(true_label)
            y_pred.append(pred_label)
            valid_count += 1

    print(f"👉 검증 가능한(키워드 포함) 데이터: {valid_count}개")

    if valid_count < 10:
        print("⚠️ 검증할 데이터가 너무 적습니다. (키워드가 포함된 글이 샘플에 적음)")
        return

    # 3. 혼동 행렬 (Confusion Matrix) 출력
    labels = ['negative', 'neutral', 'positive']
    # 실제로는 neutral 키워드를 정의 안 했으므로 neg/pos 위주로 봅니다.
    unique_labels = sorted(list(set(y_true + y_pred)))
    
    print("\n[1] 혼동 행렬 (Confusion Matrix)")
    print("   (세로: 정답, 가로: 예측값)")
    cm = confusion_matrix(y_true, y_pred, labels=unique_labels)
    cm_df = pd.DataFrame(cm, index=[f"True {l}" for l in unique_labels], columns=[f"Pred {l}" for l in unique_labels])
    print(cm_df)

    # 4. 분류 리포트 (Precision, Recall, F1-Score)
    print("\n[2] 상세 성적표 (Classification Report)")
    print(classification_report(y_true, y_pred, labels=unique_labels, zero_division=0))

def run_validation():
    engine = create_engine(f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
    
    # 뉴스 데이터 검증
    calculate_metrics_for_table("news_data", engine)
    
    print("\n" + "="*50 + "\n")
    
    # 커뮤니티 데이터 검증
    calculate_metrics_for_table("community_data", engine)

if __name__ == "__main__":
    run_validation()