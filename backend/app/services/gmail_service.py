"""Gmail API를 통해 Excel/CSV 첨부파일을 가져오는 서비스.

사전 준비:
  1. Google Cloud Console에서 OAuth 2.0 클라이언트 ID를 생성하고
     credentials.json 을 프로젝트 루트(또는 GMAIL_CREDENTIALS_PATH 환경변수 경로)에 저장.
  2. 최초 실행 시 브라우저 인증 후 token.json 이 자동 생성됨.

환경변수(선택):
  GMAIL_CREDENTIALS_PATH  - credentials.json 경로 (기본: credentials.json)
  GMAIL_TOKEN_PATH         - token.json 경로 (기본: token.json)
  GMAIL_USER_ID            - Gmail 계정 (기본: me)
"""

import base64
import os
from datetime import date

# Gmail API 읽기 권한만 요청
_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

_CREDENTIALS_PATH = os.getenv("GMAIL_CREDENTIALS_PATH", "credentials.json")
_TOKEN_PATH = os.getenv("GMAIL_TOKEN_PATH", "token.json")
_USER_ID = os.getenv("GMAIL_USER_ID", "me")


def _get_credentials():
    """저장된 token.json 을 읽거나, 없으면 OAuth2 인증 흐름을 실행해 갱신."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as e:
        raise RuntimeError(
            "Google 라이브러리가 설치되지 않았습니다. "
            "pip install google-auth-oauthlib google-api-python-client 를 실행하세요."
        ) from e

    creds = None

    if os.path.exists(_TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(_TOKEN_PATH, _SCOPES)

    # 유효하지 않거나 만료된 경우 갱신
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(_CREDENTIALS_PATH, _SCOPES)
            creds = flow.run_local_server(port=0)
        # 갱신된 토큰 저장
        with open(_TOKEN_PATH, "w", encoding="utf-8") as token_file:
            token_file.write(creds.to_json())

    return creds


def fetch_latest_attachment(target_date: date) -> tuple[str, bytes]:
    """지정한 날짜의 Gmail 에서 Excel/CSV 첨부파일을 가져온다.

    Args:
        target_date: 검색할 이메일 날짜 (after:{date} 쿼리 사용).

    Returns:
        (file_name, file_bytes) 튜플.
        해당 날짜에 첨부파일이 없으면 FileNotFoundError 를 발생시킨다.
    """
    from googleapiclient.discovery import build
    creds = _get_credentials()
    service = build("gmail", "v1", credentials=creds)

    # 검색 쿼리: 해당 날짜 이후 Excel 또는 CSV 첨부파일
    date_str = target_date.strftime("%Y/%m/%d")
    query = f"has:attachment (filename:xlsx OR filename:csv) after:{date_str}"

    response = (
        service.users()
        .messages()
        .list(userId=_USER_ID, q=query, maxResults=10)
        .execute()
    )
    messages: list[dict] = response.get("messages", [])

    if not messages:
        raise FileNotFoundError(
            f"{target_date} 날짜에 Excel/CSV 첨부파일이 있는 이메일을 찾을 수 없습니다."
        )

    # 가장 최근 메시지(첫 번째)에서 첨부파일 추출
    msg_id: str = messages[0]["id"]
    message = (
        service.users().messages().get(userId=_USER_ID, id=msg_id).execute()
    )

    payload: dict = message.get("payload", {})
    parts: list[dict] = payload.get("parts", [])

    # 재귀적으로 파트를 탐색해 첨부파일 찾기
    file_name, file_data = _find_attachment(service, msg_id, parts)
    return file_name, file_data


def _find_attachment(
    service, msg_id: str, parts: list[dict]
) -> tuple[str, bytes]:
    """파트 목록을 재귀 탐색하여 첫 번째 Excel/CSV 첨부파일을 반환."""
    for part in parts:
        # 중첩 파트 재귀 처리
        sub_parts = part.get("parts", [])
        if sub_parts:
            try:
                return _find_attachment(service, msg_id, sub_parts)
            except FileNotFoundError:
                pass

        filename: str = part.get("filename", "")
        if not filename:
            continue

        lower_name = filename.lower()
        if not (lower_name.endswith(".xlsx") or lower_name.endswith(".csv")):
            continue

        body: dict = part.get("body", {})
        attachment_id: str | None = body.get("attachmentId")

        if attachment_id:
            attachment = (
                service.users()
                .messages()
                .attachments()
                .get(userId=_USER_ID, messageId=msg_id, id=attachment_id)
                .execute()
            )
            data: str = attachment.get("data", "")
        else:
            # 소용량 첨부파일은 body.data 에 직접 포함
            data = body.get("data", "")

        if not data:
            continue

        # Gmail API 는 URL-safe Base64 인코딩을 사용
        file_bytes = base64.urlsafe_b64decode(data)
        return filename, file_bytes

    raise FileNotFoundError("파트에서 Excel/CSV 첨부파일을 찾을 수 없습니다.")
