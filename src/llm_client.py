# 작성일: 2026-06-19
# 설계자: 김유상
# 설계자 소속: 경포씨엔씨
# 설계자 이메일: bakkus@kpcnc.co.kr, bakkus@daum.net

"""통합 YAML 설정을 기반으로 공용 LLM 모듈을 활용하여 사용자의 질문을 라우팅하고 일반 답변을 생성하는 모듈입니다."""

import json
from agent_common.config_loader import setting
from agent_common.llm import LlmClient as SharedLlmClient


class LlmClient:
    """공용 LlmClient를 내부적으로 관리하여 의도 분류 및 일반 대화 응답 생성을 수행하는 클래스입니다."""

    # 공용 LLM 클라이언트 인스턴스입니다.
    # 허용 범위: SharedLlmClient 객체 구조입니다.
    _shared_client: SharedLlmClient

    def __init__(self) -> None:
        """라우터(의도 분류 및 대화) 목적을 지정하여 공용 LLM 클라이언트를 초기화합니다."""
        # purpose="router"로 초기화하여 설정의 llm.router_model(예: openai_gpt4o)을 활용합니다.
        self._shared_client = SharedLlmClient(purpose="router")

    def classify_query(self, query: str) -> str:
        """사용자 질문이 SQL 생성 요구사항인지 일반 대화인지 분류합니다.

        Args:
            query: 사용자의 자연어 입력 질문.

        Returns:
            "SQL_GENERATION" 또는 "GENERAL" 카테고리 식별값.
        """
        system_prompt = str(setting("prompts.routing_system_prompt"))
        raw_response = self._shared_client.generate(prompt=query, system_prompt=system_prompt)
        if not raw_response:
            return "GENERAL"
        
        raw_response = raw_response.strip()

        # JSON 형식 정제 및 파싱 시도
        # 마크다운 백틱(```json ... ```) 제거
        if raw_response.startswith("```"):
            lines = raw_response.splitlines()
            if len(lines) >= 2:
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines[-1].strip() == "```":
                    lines = lines[:-1]
                raw_response = "\n".join(lines).strip()

        try:
            parsed = json.loads(raw_response)
            category = parsed.get("category", "GENERAL").upper()
            if category in {"SQL_GENERATION", "GENERAL"}:
                return category
        except (json.JSONDecodeError, AttributeError):
            pass

        # 파싱 실패 혹은 유효하지 않은 카테고리의 경우 휴리스틱 분류
        lower_query = query.lower()
        sql_keywords = {"sql", "쿼리", "테이블", "조회", "데이터", "주문수", "매출", "개수", "목록", "주문", "합계", "평균"}
        if any(keyword in lower_query for keyword in sql_keywords):
            return "SQL_GENERATION"

        return "GENERAL"

    def generate_general_response(self, query: str) -> str:
        """일반 질문에 대한 친근한 한국어 답변을 생성합니다.

        Args:
            query: 사용자의 자연어 입력 질문.

        Returns:
            LLM이 생성한 한글 응답 메시지.
        """
        system_prompt = str(setting("prompts.general_system_prompt"))
        res = self._shared_client.generate(prompt=query, system_prompt=system_prompt)
        return res if res else "죄송합니다. 답변을 생성하지 못했습니다."
