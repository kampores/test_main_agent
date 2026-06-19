# 작성일: 2026-06-18
# 설계자: 김유상
# 설계자 소속: 경포씨엔씨
# 설계자 이메일: bakkus@kpcnc.co.kr, bakkus@daum.net

"""LangGraph를 활용하여 중앙 에이전트의 상태 흐름과 Human-in-the-Loop을 구현하는 모듈입니다."""

from typing import TypedDict, Any, Dict, Literal
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from llm_client import LlmClient
from sql_api_client import SqlApiClient
from agent_common.logging_config import ProjectLogger

logger = ProjectLogger.get_logger("agent.graph")

# 하위 에이전트 및 연동 객체 싱글톤 선언
_llm_client = LlmClient()
_sql_client = SqlApiClient()


class AgentState(TypedDict):
    """중앙 에이전트의 대화 상태 정보를 저장하는 스키마입니다."""
    
    # 사용자가 입력한 원본 자연어 질문 문자열입니다.
    query: str
    
    # 질문에 대한 의도 분류 카테고리 결과 값입니다. ("SQL_GENERATION" 또는 "GENERAL")
    category: str
    
    # SQL 생성 시 백엔드 서비스로 전달할 생성 모드 값입니다. ("auto", "metricflow", "llm", "fallback", "cancelled")
    generation_mode: str
    
    # 최종적으로 연동 및 처리 완료된 응답 상세 데이터입니다.
    response: Any
    
    # 인간 개입 및 추가 의사결정을 대기하고 있는지 여부를 나타내는 플래그입니다.
    is_waiting_clarification: bool
    
    # 런타임 처리 중 발생한 예외 에러 메시지 문자열입니다.
    error: str | None


def classify_node(state: AgentState) -> Dict[str, Any]:
    """사용자의 자연어 입력 질문을 분석하여 의도(SQL 생성 혹은 일반 대화)를 분류합니다.

    Args:
        state: 현재 에이전트 상태 딕셔너리.

    Returns:
        의도 분류 결과가 업데이트된 상태 딕셔너리.
    """
    query = state["query"]
    category = _llm_client.classify_query(query)
    logger.info("classify_node - 질문: '%s', 의도 분류: %s", query, category)
    return {"category": category}


def generate_sql_node(state: AgentState) -> Dict[str, Any]:
    """FastAPI SQL 생성 서비스 API를 호출하여 SQL을 생성하고 결과를 수집합니다.

    Args:
        state: 현재 에이전트 상태 딕셔너리.

    Returns:
        SQL 생성 결과 또는 일시정지 상태 지시자가 담긴 업데이트 상태 딕셔너리.
    """
    query = state["query"]
    mode = state.get("generation_mode", "auto")
    
    logger.info("generate_sql_node - SQL 생성 API 호출 시도 (모드: %s)", mode)
    
    try:
        result = _sql_client.generate_sql(query, mode)
        return {
            "response": result,
            "is_waiting_clarification": False,
            "error": None
        }
    except Exception as e:
        # MetricFlow 전용 생성 요청 중 에러가 발생한 경우 일시정지(Interrupt) 플래그를 설정하여 대기 처리
        if mode == "metricflow":
            logger.warning("generate_sql_node - MetricFlow 생성 실패. 사용자 피드백 대기 상태로 전환합니다. 오류: %s", e)
            return {
                "response": "MetricFlow로 SQL을 생성하는 데 실패했습니다. 일반 LLM 모드로 재시도하시겠습니까?",
                "is_waiting_clarification": True,
                "error": str(e)
            }
        else:
            # 기타 자동 모드 및 일반 에러 상황은 예외를 직접 전파하거나 기록
            logger.error("generate_sql_node - SQL 생성 에러 발생: %s", e)
            raise e


def general_chat_node(state: AgentState) -> Dict[str, Any]:
    """일반 대화 모델을 호출하여 한글 응답 대화를 구성합니다.

    Args:
        state: 현재 에이전트 상태 딕셔너리.

    Returns:
        대화 응답 내용이 업데이트된 상태 딕셔너리.
    """
    query = state["query"]
    response_text = _llm_client.generate_general_response(query)
    logger.info("general_chat_node - 일반 대화 답변 생성 완료.")
    return {"response": response_text.strip()}


def ask_human_node(state: AgentState) -> Dict[str, Any]:
    """인간의 입력 동의 여부를 대기하는 자리표시기(Placeholder) 노드입니다.

    해당 노드 진입 직전 그래프가 일시정지(Interrupt)되도록 설계되었습니다.

    Args:
        state: 현재 에이전트 상태 딕셔너리.

    Returns:
        상태 변경이 없는 빈 딕셔너리.
    """
    logger.info("ask_human_node - 사용자 동의 여부 재개 완료. 선택된 모드: %s", state.get("generation_mode"))
    return {}


# 조건부 에지 정의 함수
def route_after_classify(state: AgentState) -> Literal["generate_sql", "general_chat"]:
    """의도 분류 결과에 따라 SQL 생성 또는 일반 대화 노드로 분기합니다."""
    if state["category"] == "SQL_GENERATION":
        return "generate_sql"
    return "general_chat"


def route_after_sql(state: AgentState) -> Literal["ask_human", "__end__"]:
    """SQL 생성 시도 후, 사용자 질문 동의가 요구되는 경우와 완료된 경우를 분기합니다."""
    if state.get("is_waiting_clarification", False):
        return "ask_human"
    return "__end__"


def route_after_human(state: AgentState) -> Literal["generate_sql", "__end__"]:
    """사용자 재시도 승인 여부에 따라 SQL을 재생성할지 혹은 취소하고 종료할지 분기합니다."""
    mode = state.get("generation_mode")
    if mode == "llm":
        return "generate_sql"
    # 승인 거절 또는 취소의 경우 즉시 종료
    return "__end__"


# LangGraph 상태 그래프 설계 및 컴파일
builder = StateGraph(AgentState)

# 노드 등록
builder.add_node("classify", classify_node)
builder.add_node("generate_sql", generate_sql_node)
builder.add_node("general_chat", general_chat_node)
builder.add_node("ask_human", ask_human_node)

# 에지 흐름 구성
builder.add_edge(START, "classify")

# 조건부 분기 등록
builder.add_conditional_edges(
    "classify",
    route_after_classify,
    {
        "generate_sql": "generate_sql",
        "general_chat": "general_chat"
    }
)

builder.add_conditional_edges(
    "generate_sql",
    route_after_sql,
    {
        "ask_human": "ask_human",
        "__end__": END
    }
)

builder.add_conditional_edges(
    "ask_human",
    route_after_human,
    {
        "generate_sql": "generate_sql",
        "__end__": END
    }
)

builder.add_edge("general_chat", END)

# 메모리 기반 체크포인터 생성 및 컴파일 연동
# ask_human 노드가 실행되기 직전에 일시정지(Interrupt)하도록 구성
memory = MemorySaver()
agent_graph = builder.compile(
    checkpointer=memory,
    interrupt_before=["ask_human"]
)
