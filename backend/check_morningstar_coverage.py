"""Morningstar Redash 데이터와 우리은행 K55 코드 교차 확인."""
import sys, os, base64
import pandas as pd
sys.path.insert(0, r"C:\Users\김효진\2.FinancialData\backend")
os.chdir(r"C:\Users\김효진\2.FinancialData\backend")

from dotenv import load_dotenv
load_dotenv(".env")

from app.core.config import settings
from app.services.redash_client import RedashClient
from app.services.bank_import_service import (
    _get_gmail_service, _find_attachment, _parse_attachment,
    INSTITUTIONS, _load_krz_to_k55
)

# 우리은행 K55 코드 수집
krz_to_k55 = _load_krz_to_k55()
service = _get_gmail_service()
cfg = next(c for c in INSTITUTIONS if c.key == "woori")
resp = service.users().messages().list(userId="me", q=cfg.query, maxResults=3).execute()
msg = None
for m in resp.get("messages", []):
    candidate = service.users().messages().get(userId="me", id=m["id"]).execute()
    hdrs = {h["name"]: h["value"] for h in candidate["payload"]["headers"]}
    if "우리자산운용" not in hdrs.get("Subject", ""):
        msg = candidate; break

att = _find_attachment(msg["payload"].get("parts", []))
fname, att_id = att
att_resp = service.users().messages().attachments().get(userId="me", messageId=msg["id"], id=att_id).execute()
df = _parse_attachment(base64.urlsafe_b64decode(att_resp["data"]), fname)
c = cfg.resolve(df)
active_df = df.copy()
if c["avail"]: active_df = active_df[active_df[c["avail"]].str.upper() == "Y"]
if c["end"]: active_df = active_df[active_df[c["end"]].str.replace("-","") == "99991231"]

krz_codes = [str(r).strip() for r in active_df[c["etf_code"] or c["fund_code"]].dropna() if str(r).startswith("KRZ")]
woori_k55 = list({krz_to_k55[k] for k in krz_codes if k in krz_to_k55})
print(f"우리은행 K55 코드: {len(woori_k55)}개")

redash = RedashClient(base_url=settings.redash_url, api_key=settings.redash_api_key)

# Morningstar 전체 건수
rows = redash.run_query(25, """
SELECT COUNT(*) AS total, COUNT(krcode) AS with_krcode
FROM iceberg.morningstar_fund.operation
WHERE pit = (SELECT MAX(pit) FROM iceberg.morningstar_fund.operation)
""")
print(f"\nMorningstar 전체: {rows}")

# 우리은행 K55 코드가 Morningstar에 있는지 (전체)
k55_list = "','".join(woori_k55)
rows2 = redash.run_query(25, f"""
SELECT COUNT(*) AS cnt
FROM iceberg.morningstar_fund.operation
WHERE pit = (SELECT MAX(pit) FROM iceberg.morningstar_fund.operation)
  AND krcode IN ('{k55_list}')
""")
print(f"\nMorningstar에 있는 우리은행 K55: {rows2}")
