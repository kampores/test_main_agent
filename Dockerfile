# 1. Python 3.12 런타임 베이스 이미지 설정
FROM python:3.12-slim

# 2. 파이썬 버퍼 비활성화 및 UTF-8 타임존 인코딩 환경 설정
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

WORKDIR /workspace

# 3. 공용 라이브러리(agent_common) 복사 및 로컬 패키지 형태로 사전 설치
# (상위 build context 기준인 Downloads/code에서 빌드가 전개됨)
COPY ./agent_common /workspace/agent_common
RUN pip install --no-cache-dir -e /workspace/agent_common

# 4. 중앙 에이전트 프로젝트 의존성 설치 및 파일 복사
COPY ./test_main_agent/requirements.txt /workspace/test_main_agent/requirements.txt
RUN pip install --no-cache-dir -r /workspace/test_main_agent/requirements.txt

COPY ./test_main_agent /workspace/test_main_agent

# 5. 설정(config_loader) 탐색 기준에 부합하도록 작업 디렉토리를 프로젝트 루트로 지정
WORKDIR /workspace/test_main_agent

# 6. 에이전트 API 서버 포트 노출
EXPOSE 8080

# 7. FastAPI 서버 기동 엔트리포인트 지정
CMD ["python", "src/main.py"]
