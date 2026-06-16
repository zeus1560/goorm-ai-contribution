import pandas as pd
from sqlalchemy import create_engine, text
from sklearn.metrics import classification_report, confusion_matrix
import sys

# ==========================================
# 1. DB 설정
# ==========================================
DB_USER = "postgres"
DB_PASSWORD = "0000"
DB_HOST = "localhost"
DB_PORT = "15432"
DB_NAME = "app"

def interactive_scoring():
    engine = create_engine(f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
    
    print("\n======== 👨‍🏫 [AI 채점 시간] 사용자 참여형 검증 ========")
    print("   👉 AI가 분류한 글을 보여드립니다.")
    print("   👉 사용자님이 보시기에 '진짜 정답'을 입력해주세요.")
    print("   👉 (총 30문제입니다. 화이팅!)\n")

    # 1. 무작위 데이터 가져오기 (각 10개씩)
    dfs = []
    with engine.connect() as conn:
        for label in ['positive', 'negative', 'neutral']:
            query = text(f"""
                SELECT community_id, title, COALESCE(description, '') as desc_text, sentiment_label 
                FROM community_data 
                WHERE sentiment_label = '{label}'
                ORDER BY RANDOM() 
                LIMIT 10
            """)
            dfs.append(pd.read_sql(query, conn))
    
    full_df = pd.concat(dfs).sample(frac=1).reset_index(drop=True) # 섞기
    
    y_true = [] # 사용자님이 입력할 진짜 정답
    y_pred = [] # AI가 예측한 값
    
    # 2. 문제 풀기 (Loop)
    correct_count = 0
    
    for i, row in full_df.iterrows():
        ai_pick = row['sentiment_label']
        text_content = f"{row['title']} {row['desc_text']}".strip()[:100].replace("\n", " ")
        
        print(f"\n[{i+1}/30] ---------------------------------------------------")
        print(f"📝 내용: {text_content}...")
        print(f"🤖 AI 생각: [{ai_pick.upper()}]")
        
        while True:
            user_input = input("👨‍⚖️ 당신의 판결은? (1: 긍정, 2: 부정, 3: 중립, s: 스킵): ").strip()
            
            if user_input == '1':
                human_label = 'positive'
                break
            elif user_input == '2':
                human_label = 'negative'
                break
            elif user_input == '3':
                human_label = 'neutral'
                break
            elif user_input.lower() == 's':
                human_label = None
                print("   -> 넘어갑니다.")
                break
            else:
                print("⚠️ 잘못된 입력입니다. 1, 2, 3 중에 골라주세요.")
        
        if human_label:
            y_true.append(human_label)
            y_pred.append(ai_pick)
            if human_label == ai_pick:
                print("   ✅ 정답! (AI와 생각이 같습니다)")
                correct_count += 1
            else:
                print(f"   ❌ 오답... (사용자: {human_label.upper()} vs AI: {ai_pick.upper()})")

    # 3. 성적표 출력
    if not y_true:
        print("\n채점한 데이터가 없습니다.")
        return

    print("\n" + "="*50)
    print(f"📊 최종 성적표 (총 {len(y_true)}문제 중 {correct_count}개 일치)")
    print("="*50)

    labels = ['negative', 'neutral', 'positive']
    
    # 혼동 행렬
    print("\n[1] 혼동 행렬 (Confusion Matrix)")
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    cm_df = pd.DataFrame(cm, index=[f"True {l}" for l in labels], columns=[f"Pred {l}" for l in labels])
    print(cm_df)
    
    # F1 Score 리포트
    print("\n[2] 상세 점수 (Classification Report)")
    print(classification_report(y_true, y_pred, labels=labels, zero_division=0))

if __name__ == "__main__":
    interactive_scoring()