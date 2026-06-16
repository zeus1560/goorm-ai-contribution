#!/bin/bash

# 색상 정의
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 [HeartBit] 시스템 가동을 시작합니다...${NC}"

# 1. Qdrant 상태 체크 (포트 6333 확인)
if ! nc -z localhost 6333; then
    echo -e "${RED}❌ Qdrant 서버가 작동 중이지 않습니다. 도커 컨테이너를 먼저 확인하세요.${NC}"
    exit 1
fi
echo -e "✅ Qdrant 서버 연결 확인됨."

# 2. 기존 프로세스 정리
echo "🧹 기존 프로세스 종료 중..."
pkill -f news_collector.py
pkill -f community_aggregator.py
pkill -f sentiment_analyzer.py
pkill -f main.py  # RAG 메인 에이전트
sleep 2

# 3. 로그 폴더 생성
mkdir -p logs
rm -f logs/*.log
PYTHON_CMD="venv/bin/python -u"

# 4. 각 컴포넌트 백그라운드 실행
echo "▶️ 1. 뉴스 수집기 시작..."
nohup $PYTHON_CMD src/collectors/news_collector.py > logs/news.log 2>&1 &

echo "▶️ 2. 커뮤니티 수집기 시작..."
nohup $PYTHON_CMD src/collectors/community_aggregator.py > logs/community.log 2>&1 &

echo "▶️ 3. 감성 분석기 시작..."
nohup $PYTHON_CMD src/analysis/sentiment_analyzer.py > logs/sentiment.log 2>&1 &

echo "▶️ 4. AI 분석기(RAG Agent) 시작..."
nohup $PYTHON_CMD src/main.py > logs/agent.log 2>&1 &

# 5. 실행 상태 확인
sleep 3
echo -e "\n${GREEN}📊 프로세스 가동 상태 확인:${NC}"
for proc in "news_collector.py" "community_aggregator.py" "sentiment_analyzer.py" "main.py"; do
    if pgrep -f "$proc" > /dev/null; then
        echo -e "  - $proc: ${GREEN}RUNNING${NC}"
    else
        echo -e "  - $proc: ${RED}FAILED${NC}"
    fi
done

echo -e "\n${GREEN}✅ 모든 시스템 설정이 완료되었습니다.${NC}"