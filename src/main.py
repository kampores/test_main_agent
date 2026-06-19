# 작성일: 2026-06-18
# 설계자: 김유상
# 설계자 소속: 경포씨엔씨
# 설계자 이메일: bakkus@kpcnc.co.kr, bakkus@daum.net

"""중앙 라우팅 에이전트의 FastAPI 웹 API 진입점 및 서비스 구현 모듈입니다.

LangGraph 상태 그래프와 MemorySaver를 활용하여 Human-in-the-Loop을 구현합니다.
"""

import os
import sys
import uuid
from pathlib import Path
from time import perf_counter

# src 디렉터리를 sys.path에 추가하여 형제 모듈 임포트를 안전하게 처리합니다.
src_path = str(Path(__file__).resolve().parent)
if src_path not in sys.path:
    sys.path.insert(0, src_path)
import uvicorn
import requests
from typing import Any, Optional
from fastapi import FastAPI, HTTPException, status, Request
from pydantic import BaseModel, Field

from agent_common.config_loader import setting, project_path
from agent_common.logging_config import ProjectLogger
from agent_common.error_handler import ErrorHandler
from agent_graph import agent_graph

# ProjectLogger 설정 및 로거 인스턴스 획득
ProjectLogger.configure(setting, project_path)
logger = ProjectLogger.get_logger("agent")

# FastAPI 애플리케이션 생성 정보 구성
app_kwargs = {}
api_title = setting("agent_api.title")
if api_title is not None:
    app_kwargs["title"] = str(api_title)
api_version = setting("agent_api.version")
if api_version is not None:
    app_kwargs["version"] = str(api_version)
api_description = setting("agent_api.description")
if api_description is not None:
    app_kwargs["description"] = str(api_description)

# FastAPI 인스턴스 초기화
app = FastAPI(**app_kwargs)

# 공통 에러 핸들러 등록
ErrorHandler.register_fastapi_handlers(app)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """HTTP 요청 처리 시간과 오류를 로그로 남긴다."""
    start = perf_counter()
    access_log_enabled = bool(setting("logging.access_log", True))
    if access_log_enabled:
        logger.info("request_start method=%s path=%s", request.method, request.url.path)
    try:
        response = await call_next(request)
    except Exception as exc:
        ProjectLogger.log_request_result(logger, request.method, request.url.path, start, exc=exc)
        raise

    if access_log_enabled:
        ProjectLogger.log_request_result(
            logger, request.method, request.url.path, start, status_code=response.status_code
        )
    return response


class QueryRequest(BaseModel):
    """사용자가 전송한 질문 요청 스키마입니다."""
    
    # 사용자가 작성한 자연어 질문 데이터입니다.
    # 허용 범위: 공백이 아닌 최소 1자 이상의 문자열이며, 의도 분류기 및 대상 에이전트로 전달되어 분석됩니다. 신규 질문 시 필수이며, 세션 재개 시 생략 가능합니다.
    query: Optional[str] = Field(None, description="의도 분석 및 라우팅 대상이 되는 자연어 질문.")
    
    # SQL 생성 시 시도할 최초 경로 모드입니다.
    # 허용 범위: "auto", "metricflow", "llm", "fallback" 문자열 중 하나입니다.
    generation_mode: str = Field("auto", description="SQL 생성 시도 모드 (auto, metricflow, llm, fallback)")
    
    # 인간 개입 상태(일시정지)에서 대화를 재개할 때 사용할 고유한 대화 세션 ID 키값입니다.
    # 허용 범위: 이전에 응답으로 수신한 유효한 UUID 문자열입니다.
    session_id: Optional[str] = Field(None, description="대화식 루프 혹은 HITL 상태 재개를 위한 세션 ID.")
    
    # MetricFlow 생성 실패 시, 차선책(일반 LLM 모드)으로 재시도하는 것을 동의하는지 여부입니다.
    # 허용 범위: 참(True)인 경우 LLM 재시도를 진행하며, 거짓(False)인 경우 중단합니다.
    approval: Optional[bool] = Field(None, description="MetricFlow 실패 시 LLM 폴백 진행 동의 여부.")


class QueryResponse(BaseModel):
    """중앙 에이전트의 처리 결과 응답 스키마입니다."""
    
    # 질문의 의도 분석을 완료한 결과 카테고리값입니다.
    # 허용 범위: "SQL_GENERATION" 또는 "GENERAL" 문자열이며, 클라이언트가 응답 포맷을 분기하는 데 사용됩니다.
    category: str = Field(..., description="질문 의도 분류 결과 (SQL_GENERATION 또는 GENERAL).")
    
    # 카테고리 유형에 맞추어 처리된 응답 상세 데이터입니다.
    # 허용 범위: 일반 대화의 경우 문자열 답변, SQL 생성인 경우 생성 상세 내역을 포함하는 JSON 딕셔너리 구조입니다.
    response: Any = Field(..., description="상세 결과 데이터 (일반 답변 텍스트 또는 SQL 생성기 API의 응답 데이터).")
    
    # 현재 에이전트 상태를 이어서 진행하기 위한 대화 세션 ID입니다.
    # 허용 범위: 128비트 크기의 UUID 규격 문자열입니다.
    session_id: str = Field(..., description="HITL 상태 추적 및 대화 재개를 위한 대화 세션 ID.")
    
    # 현재 에이전트가 인간의 동의 및 결정을 대기하고 있는지 여부를 나타냅니다.
    # 허용 범위: 참(True)인 경우 추가 동의(approval) 응답이 필요하며, 거짓(False)인 경우 최종 응답임을 뜻합니다.
    is_waiting_clarification: bool = Field(False, description="사용자 피드백(승인/반려) 대기 상태 플래그.")


@app.get("/health")
def health() -> dict[str, str]:
    """에이전트 서비스의 동작 상태를 확인하는 헬스체크 API입니다.

    Returns:
        정상 구동 상태 정보 딕셔너리.
    """
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse)
def query_endpoint(request: QueryRequest) -> QueryResponse:
    """사용자의 질문을 수신하여 LangGraph 워크플로우에 따라 라우팅하고 인간 개입 필요 시 일시정지 및 재개를 제어합니다.

    Args:
        request: 사용자 입력 파라미터가 담긴 요청 객체.

    Returns:
        워크플로우 실행 결과 응답 객체.
    """
    # 1. 신규 대화 세션 시작 처리
    if not request.session_id:
        query = request.query
        if not query or not query.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="신규 세션 시작 시 query(질문) 필드는 필수 입력 항목입니다."
            )
        
        session_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": session_id}}
        
        initial_state = {
            "query": query.strip(),
            "category": "GENERAL",
            "generation_mode": request.generation_mode,
            "response": None,
            "is_waiting_clarification": False,
            "error": None
        }
        
        logger.info("query_endpoint - 신규 세션 생성. ID: %s, 모드: %s", session_id, request.generation_mode)
        
        try:
            # LangGraph 실행 (ask_human 노드 직전까지 수행)
            agent_graph.invoke(initial_state, config)
        except requests.exceptions.ConnectionError as e:
            logger.error("classify_query_network_error - 연결 실패: %s", e)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"연결 오류가 발생했습니다. 서비스 연결 상태를 확인해 주세요. 세부정보: {e}"
            )
        except requests.exceptions.HTTPError as e:
            logger.warning("sql_backend_http_error - HTTP 응답 오류: %s", e)
            try:
                error_detail = e.response.json().get("detail", str(e))
            except Exception:
                error_detail = str(e)
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"백엔드 서비스 오류: {error_detail}"
            )
        except Exception as e:
            logger.error("graph_invocation_error - 그래프 실행 중 오류: %s", e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"그래프 실행 과정 중 예외가 발생했습니다: {e}"
            )

    # 2. 기존 대화 세션 재개 처리 (HITL)
    else:
        session_id = request.session_id
        config = {"configurable": {"thread_id": session_id}}
        
        # 이전 체크포인트 상태 조회
        state_info = agent_graph.get_state(config)
        if not state_info or not state_info.values:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"지정된 session_id '{session_id}'에 해당하는 대화 세션을 찾을 수 없습니다."
            )
        
        if request.approval is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="대화 세션 재개 시 approval(동의 여부) 필드는 필수 입력 항목입니다."
            )
            
        next_mode = "llm" if request.approval else "cancelled"
        logger.info("query_endpoint - 세션 재개. ID: %s, 승인 결과: %s, 다음 모드: %s", session_id, request.approval, next_mode)
        
        try:
            # 사용자 승인 여부에 따라 에이전트 상태 업데이트 및 일시정지 해제
            agent_graph.update_state(config, {
                "generation_mode": next_mode,
                "is_waiting_clarification": False
            }, as_node="ask_human")
            
            # 그래프 재개
            agent_graph.invoke(None, config)
        except requests.exceptions.ConnectionError as e:
            logger.error("classify_query_network_error - 연결 실패: %s", e)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"연결 오류가 발생했습니다. 서비스 연결 상태를 확인해 주세요. 세부정보: {e}"
            )
        except requests.exceptions.HTTPError as e:
            logger.warning("sql_backend_http_error - HTTP 응답 오류: %s", e)
            try:
                error_detail = e.response.json().get("detail", str(e))
            except Exception:
                error_detail = str(e)
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"백엔드 서비스 오류: {error_detail}"
            )
        except Exception as e:
            logger.error("graph_resume_error - 그래프 재개 중 오류: %s", e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"그래프 재개 과정 중 예외가 발생했습니다: {e}"
            )

    # 3. 최종 상태 반환
    final_state = agent_graph.get_state(config).values
    return QueryResponse(
        category=final_state.get("category", "GENERAL"),
        response=final_state.get("response"),
        session_id=session_id,
        is_waiting_clarification=final_state.get("is_waiting_clarification", False)
    )


def main() -> None:
    """설정 파일에서 로드된 호스트 및 포트 정보를 활용하여 uvicorn 서버를 시작합니다."""
    host = str(setting("agent_api.host", "127.0.0.1"))
    port = int(setting("agent_api.port", 8080))
    reload = bool(setting("agent_api.reload", False))

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=reload,
    )


if __name__ == "__main__":
    main()
