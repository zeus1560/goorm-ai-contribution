import pandas as pd
import torch
from sqlalchemy import create_engine, text
from transformers import pipeline
from tqdm import tqdm
import sys

# ==========================================
# 1. DB 설정
# ==========================================
DB_USER = "postgres"      
DB_PASSWORD = "0000"  
DB_HOST = "localhost"          
DB_PORT = "15432"               
DB_NAME = "app"       

# ==========================================
# 2. [핵심] 코인 은어 사전
# ==========================================
SLANG_DICT = {
    # [🔴 확실한 악재]
    "떡락": " HUGE CRASH ",
    "폭락": " PLUMMET ",
    "나락": " HELL DUMP ",
    "한강": " SUICIDE DEPRESSION ",
    "돔황챠": " RUN AWAY ",
    "탈출": " ESCAPE ", 
    "손절": " PANIC SELL ",
    "설거지": " SCAM DUMP ",
    "흑우": " VICTIM ",
    "물렸": " TRAPPED LOSS ",
    "상폐": " DELISTING ",
    "스캠": " SCAM ",
    "망했": " RUINED ",
    "무섭다": " FEAR ",
    "무서워": " FEAR ",
    "공포": " FEAR ",
    "drained": " HACKED ",
    "Drained": " HACKED ",
    "털렸다": " HACKED ",
    "해킹": " HACKED ",

    # [🟢 확실한 호재]
    "떡상": " HUGE PUMP ",
    "불장": " BULL MARKET ",
    "가즈아": " TO THE MOON ",
    "존버": " HODL ",
    "홀딩": " HODL ",
    "졸업": " RETIRE RICH ",
    "익절": " TAKE PROFIT ",
    "반등": " REBOUND ",
    "말아올려": " PUMP UP ",
    "풀매수": " ALL IN BUY ",
    "롱": " LONG POSITION ",
    "구조대": " RECOVERY PRICE ",
}

def fix_critical_errors_v2():
    engine = create_engine(f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
    
    if torch.backends.mps.is_available():
        device = torch.device("mps")
    else:
        device = torch.device("cpu")

    print(f"\n======== 🚑 긴급 수정: 은어 포함 데이터 재분석 (V2) ========")

    # 1. 은어가 포함된 데이터만 SQL로 조회
    conditions = []
    for slang in SLANG_DICT.keys():
        conditions.append(f"title LIKE '%%{slang}%%'")
        conditions.append(f"description LIKE '%%{slang}%%'")
    
    where_clause = " OR ".join(conditions)
    
    query = f"""
    SELECT community_id, title, COALESCE(description, '') as description
    FROM community_data
    WHERE {where_clause}
    """
    
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    
    total_rows = len(df)
    if total_rows == 0:
        print("🎉 수정할 데이터가 없습니다.")
        return

    print(f"👉 수정 대상 발견: {total_rows}개")

    # 2. 모델 로드
    print("⏳ 모델 로딩 중...")
    translator = pipeline("translation", model="Helsinki-NLP/opus-mt-ko-en", device=device, truncation=True, max_length=512)
    classifier = pipeline("text-classification", model="ElKulako/cryptobert", device=device, truncation=True, max_length=512)

    df['full_text'] = df.apply(lambda row: f"{row['title']} {row['description']}".strip(), axis=1)

    updates = []
    batch_size = 8

    print("🌊 수술 집도 중...")

    for i in tqdm(range(0, total_rows, batch_size), desc="Fixing"):
        batch_df = df.iloc[i : i + batch_size]
        original_texts = batch_df['full_text'].tolist()
        doc_ids = batch_df['community_id'].tolist()
        
        # A. [핵심] 은어 강제 치환 (변수명 content로 수정!)
        injected_texts = []
        for content in original_texts:  # <--- 여기 수정했습니다! (text -> content)
            for slang, replacement in SLANG_DICT.items():
                if slang in content:
                    content = content.replace(slang, replacement)
            injected_texts.append(content)
        
        # B. 번역
        try:
            translated_texts = []
            results = translator(injected_texts, batch_size=len(injected_texts))
            for res in results:
                translated_texts.append(res['translation_text'])
        except:
            translated_texts = injected_texts

        # C. 감성 분석
        try:
            sentiment_results = classifier(translated_texts, batch_size=len(translated_texts))
        except:
            continue

        # D. 결과 저장 준비
        for doc_id, res in zip(doc_ids, sentiment_results):
            raw_label = res['label']
            if raw_label == 'Bullish': label = 'positive'
            elif raw_label == 'Bearish': label = 'negative'
            else: label = 'neutral'

            updates.append({
                "id": int(doc_id),
                "score": float(res['score']),
                "label": str(label)
            })

    # DB 업데이트
    if updates:
        print(f"💾 {len(updates)}건 수정 완료! (저장 시작)")
        
        # text() 함수 충돌 해결됨
        update_query = text("""
            UPDATE community_data
            SET sentiment_score = :score,
                sentiment_label = :label
            WHERE community_id = :id
        """)
        
        with engine.begin() as conn:
            conn.execute(update_query, updates)
        print("✅ 저장 완료! 이제 검증 코드를 돌리셔도 됩니다.")

if __name__ == "__main__":
    fix_critical_errors_v2()