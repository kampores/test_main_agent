# 작성일: 2026-06-18
# 설계자: 김유상
# 설계자 소속: 경포씨엔씨
# 설계자 이메일: bakkus@kpcnc.co.kr, bakkus@daum.net

"""dbt LLM SQL 생성기 API 서비스와의 HTTP 연동을 담당하는 모듈입니다."""

import requests
from typing import Any
from agent_common.config_loader import setting


class SqlApiClient:
    """FastAPI SQL 생성 서비스에 HTTP POST 요청을 전송하여 SQL 생성 결과를 받아오는 클래스입니다.

    설정 파일의 API 서버 접속 주소 및 경로 설정을 사용합니다.
    """

    # SQL 생성기 API 서버의 기본 접속 주소(URL)입니다.
    # 허용 범위: "http://" 또는 "https://"로 시작하는 유효한 URL입니다.
    _base_url: str

    # SQL 생성 엔드포인트의 리소스 경로입니다.
    # 허용 범위: "/"로 시작하는 유효한 경로 이름입니다.
    _generate_sql_path: str

    # SSL 인증서 유효성 검증을 수행할지 여부입니다.
    # 허용 범위: 불리언(True/False) 값입니다.
    _verify_ssl: bool

    def __init__(self) -> None:
        """설정 정보로부터 API 서버 연결 정보를 로드하여 인스턴스를 초기화합니다."""
        self._base_url = str(setting("api_server.base_url", "http://127.0.0.1:8000")).rstrip("/")
        self._generate_sql_path = str(setting("api_server.generate_sql_path", "/generate-sql"))
        self._verify_ssl = bool(setting("api_server.verify_ssl", True))

    def generate_sql(self, question: str, generation_mode: str = "auto") -> dict[str, Any]:
        """분석 질문을 API 서버에 전달하여 SQL 생성 응답을 받아옵니다.

        Args:
            question: 자연어로 작성된 분석 질문.
            generation_mode: SQL 생성 모드 (auto, metricflow, llm, fallback 등).

        Returns:
            API 응답 데이터 딕셔너리 (sql, sql_file_path, generated_by, warnings 등 포함).
        Raises:
            requests.RequestException: API 호출 중 네트워크 또는 서버 에러가 발생한 경우.
        """
        url = f"{self._base_url}{self._generate_sql_path}"
        payload = {
            "question": question,
            "generation_mode": generation_mode,  # 지정된 생성 경로 모드 적용
            "write_file": True          # 로컬 파일로 저장 설정 활성화
        }

        response = requests.post(url, json=payload, timeout=60, verify=self._verify_ssl)  # SQL 컴파일과 LLM 생성이 섞여 응답 지연이 발생하므로 타임아웃 60초 지정
        response.raise_for_status()
        return response.json()
