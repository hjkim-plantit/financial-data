"""kofia_fund_codes.csv에서 우리은행 K55 코드 정보 확인."""
import sys, os, base64, sqlite3
import pandas as pd
sys.path.insert(0, r"C:\Users\김효진\2.FinancialData\backend")
os.chdir(r"C:\Users\김효진\2.FinancialData\backend")

from dotenv import load_dotenv
load_dotenv(".env")
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
woori_k55 = {krz_to_k55[k] for k in krz_codes if k in krz_to_k55}

# DB에 없는 것만
conn = sqlite3.connect("fund_platform.db")
db_funds = set(r[0] for r in conn.execute("SELECT fund_code FROM funds WHERE product_type='fund'").fetchall())
conn.close()
missing_k55 = woori_k55 - db_funds
print(f"DB에 없는 우리은행 K55: {len(missing_k55)}개")

# KOFIA CSV에서 조회
kofia_df = pd.read_csv(
    r"C:\Users\김효진\2.FinancialData\kofia_fund_codes.csv",
    encoding="utf-8-sig", dtype=str
)
found = kofia_df[kofia_df["standardCd"].isin(missing_k55)]
print(f"KOFIA CSV에서 찾은 것: {len(found)}개")
print(f"\n샘플 (첫 10개):")
print(found.head(10).to_string())

# null 값 분포
print(f"\nnull 값 현황:")
print(found.isnull().sum())

# fundNm 분포 (자산군 매핑용)
print(f"\nfundNm 분포 (상위 10):")
print(found["fundNm"].value_counts().head(10))
