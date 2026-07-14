"""우리은행 이메일 K55 코드들이 KOFIA CSV에 있는지 확인."""
import sys, os
sys.path.insert(0, r"C:\Users\김효진\2.FinancialData\backend")
os.chdir(r"C:\Users\김효진\2.FinancialData\backend")

from dotenv import load_dotenv
load_dotenv(".env")

import base64, sqlite3
import pandas as pd
from app.services.bank_import_service import (
    _get_gmail_service, _find_attachment, _parse_attachment,
    INSTITUTIONS, _load_krz_to_k55
)

krz_to_k55 = _load_krz_to_k55()

# Gmail에서 우리은행 이메일 KRZ 코드 추출
service = _get_gmail_service()
cfg = next(c for c in INSTITUTIONS if c.key == "woori")
resp = service.users().messages().list(userId="me", q=cfg.query, maxResults=3).execute()

msg = None
for m in resp.get("messages", []):
    candidate = service.users().messages().get(userId="me", id=m["id"]).execute()
    hdrs = {h["name"]: h["value"] for h in candidate["payload"]["headers"]}
    if "우리자산운용" not in hdrs.get("Subject", ""):
        msg = candidate
        break

att = _find_attachment(msg["payload"].get("parts", []))
fname, att_id = att
att_resp = service.users().messages().attachments().get(userId="me", messageId=msg["id"], id=att_id).execute()
df = _parse_attachment(base64.urlsafe_b64decode(att_resp["data"]), fname)

c = cfg.resolve(df)
code_col = c["etf_code"] or c["fund_code"]
avail_col = c["avail"]
end_col = c["end"]

active_df = df.copy()
if avail_col:
    active_df = active_df[active_df[avail_col].str.upper() == "Y"]
if end_col:
    active_df = active_df[active_df[end_col].str.replace("-", "") == "99991231"]

krz_codes = [str(r).strip() for r in active_df[code_col].dropna() if str(r).startswith("KRZ")]
woori_k55_codes = set()
for krz in krz_codes:
    k55 = krz_to_k55.get(krz)
    if k55:
        woori_k55_codes.add(k55)

print(f"우리은행 펀드 KRZ: {len(krz_codes)}개")
print(f"변환된 K55: {len(woori_k55_codes)}개")

# KOFIA CSV에서 확인
kofia_df = pd.read_csv(
    r"C:\Users\김효진\2.FinancialData\kofia_fund_codes.csv",
    encoding="utf-8-sig", dtype=str
)
print(f"\nKOFIA CSV 총 건수: {len(kofia_df)}")
print(f"KOFIA CSV 컬럼: {kofia_df.columns.tolist()}")

kofia_codes = set(kofia_df["standardCd"].dropna())
in_kofia = woori_k55_codes & kofia_codes
print(f"\n우리은행 K55 중 KOFIA CSV에 있는 것: {len(in_kofia)} / {len(woori_k55_codes)}")

# DB에서 확인
conn = sqlite3.connect("fund_platform.db")
db_funds = set(r[0] for r in conn.execute("SELECT fund_code FROM funds WHERE product_type='fund'").fetchall())
conn.close()

in_db = woori_k55_codes & db_funds
not_in_db = woori_k55_codes - db_funds
in_kofia_not_db = in_kofia - db_funds

print(f"우리은행 K55 중 DB에 있는 것: {len(in_db)} / {len(woori_k55_codes)}")
print(f"우리은행 K55 중 KOFIA에 있지만 DB에 없는 것: {len(in_kofia_not_db)}개")

# KOFIA에 있지만 DB에 없는 펀드들의 정보
if in_kofia_not_db:
    missing = kofia_df[kofia_df["standardCd"].isin(in_kofia_not_db)].head(10)
    print("\nKOFIA에 있지만 DB에 없는 펀드 샘플:")
    print(missing[["standardCd", "fundNm", "companyNm", "startDt", "fundGb"]].to_string())
