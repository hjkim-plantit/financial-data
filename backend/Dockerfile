FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY scripts/ scripts/

# GMAIL_TOKEN_JSON 환경변수(JSON 문자열)가 있으면 시작 시 token.json으로 저장
CMD ["sh", "-c", "\
  if [ -n \"$GMAIL_TOKEN_JSON\" ]; then echo \"$GMAIL_TOKEN_JSON\" > token.json; fi && \
  uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} \
"]
