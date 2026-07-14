"""우리은행 이메일의 KRZ 코드들이 CSV에 있는지 확인."""
import sys, os
sys.path.insert(0, r"C:\Users\김효진\2.FinancialData\backend")
os.chdir(r"C:\Users\김효진\2.FinancialData\backend")

from dotenv import load_dotenv
load_dotenv(".env")

import base64, sqlite3
import pandas as pd
from app.services.bank_import_service import (
    _get_gmail_service, _find_attachment, _parse_attachment, _kst_date,
    INSTITUTIONS, _KRZ_TO_K55, _load_krz_to_k55
)

# CSV 다시 로드 (확인용)
krz_to_k55 = _load_krz_to_k55()
print(f"KRZ->K55 매핑 로드됨: {len(krz_to_k55)}건")

# Gmail 서비스
service = _get_gmail_service()
cfg = next(c for c in INSTITUTIONS if c.key == "woori")

resp = service.users().messages().list(userId="me", q=cfg.query, maxResults=3).execute()
msgs = resp.get("messages", [])
print(f"\n우리은행 이메일 조회: {len(msgs)}건")

msg = None
for m in msgs:
    candidate = service.users().messages().get(userId="me", id=m["id"]).execute()
    hdrs = {h["name"]: h["value"] for h in candidate["payload"]["headers"]}
    if "우리자산운용" not in hdrs.get("Subject", ""):
        msg = candidate
        headers = hdrs
        break

if not msg:
    print("유효한 이메일 없음")
    sys.exit(1)

print(f"이메일 제목: {headers.get('Subject','')}")
print(f"이메일 날짜: {headers.get('Date','')}")

att = _find_attachment(msg["payload"].get("parts", []))
fname, att_id = att
att_resp = service.users().messages().attachments().get(userId="me", messageId=msg["id"], id=att_id).execute()
df = _parse_attachment(base64.urlsafe_b64decode(att_resp["data"]), fname)

c = cfg.resolve(df)
code_col = c["etf_code"] or c["fund_code"]
avail_col = c["avail"]
end_col = c["end"]
print(f"\n파일 컬럼: {df.columns.tolist()}")
print(f"사용 코드 컬럼: {code_col}, avail: {avail_col}, end: {end_col}")
print(f"전체 행수: {len(df)}")

# 판매가능 + 유효한 것만 필터링
active_df = df.copy()
if avail_col:
    active_df = active_df[active_df[avail_col].str.upper() == "Y"]
if end_col:
    active_df = active_df[active_df[end_col].str.replace("-", "") == "99991231"]

print(f"활성 상품 수: {len(active_df)}")

# KRZ 코드들 추출
krz_codes = [str(r).strip() for r in active_df[code_col].dropna() if str(r).startswith("KRZ")]
etf_codes = [str(r).strip() for r in active_df[code_col].dropna() if str(r).startswith("KR7")]
print(f"\n펀드(KRZ): {len(krz_codes)}, ETF(KR7): {len(etf_codes)}")

# CSV에 있는지 확인
in_csv = [k for k in krz_codes if k in krz_to_k55]
not_in_csv = [k for k in krz_codes if k not in krz_to_k55]
print(f"KRZ→K55 매핑 있음: {len(in_csv)}, 없음: {len(not_in_csv)}")

# K55로 변환된 것들이 DB에 있는지 확인
conn = sqlite3.connect("fund_platform.db")
db_funds = set(r[0] for r in conn.execute("SELECT fund_code FROM funds WHERE product_type='fund'").fetchall())
conn.close()

matched = [k for k in in_csv if krz_to_k55[k] in db_funds]
unmatched_no_csv = not_in_csv
unmatched_no_db = [k for k in in_csv if krz_to_k55[k] not in db_funds]

print(f"\n매칭 분석 (펀드 {len(krz_codes)}개):")
print(f"  ① CSV 없음 (KRZ 미등록): {len(unmatched_no_csv)}개")
print(f"  ② CSV 있지만 DB 없음: {len(unmatched_no_db)}개")
print(f"  ③ 최종 매칭: {len(matched)}개")

print(f"\n미등록 KRZ 샘플 (첫 10개): {not_in_csv[:10]}")
if unmatched_no_db:
    print(f"DB 없음 K55 샘플: {[krz_to_k55[k] for k in unmatched_no_db[:5]]}")
