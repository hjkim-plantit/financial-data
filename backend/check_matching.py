import sqlite3
import pandas as pd

conn = sqlite3.connect(r"C:\Users\김효진\2.FinancialData\backend\fund_platform.db")

db_funds = set(r[0] for r in conn.execute("SELECT fund_code FROM funds WHERE product_type='fund'").fetchall())
print(f"DB fund 총 건수: {len(db_funds)}")
print(f"DB fund_code 샘플: {list(db_funds)[:5]}")

csv_path = r"C:\Users\김효진\2.FinancialData\backend\data\woori_fund_checked.csv"
df = pd.read_csv(csv_path, encoding="utf-8-sig", dtype=str)
print(f"\nCSV 총 행수: {len(df)}")
print(f"CSV 컬럼: {df.columns.tolist()}")

krz_to_k55 = {}
for _, row in df.iterrows():
    krz = str(row.get("코드") or "").strip()
    k55 = str(row.get("협회표준코드") or "").strip()
    if krz.startswith("KRZ") and k55 and k55.lower() not in ("nan", ""):
        krz_to_k55[krz] = k55

print(f"\nKRZ->K55 매핑 건수: {len(krz_to_k55)}")
k55_values = set(krz_to_k55.values())
in_db = k55_values & db_funds
print(f"\nCSV K55 코드 중 DB에 있는 것: {len(in_db)} / {len(k55_values)}")
print(f"K55 코드 샘플 (DB에 있음): {list(in_db)[:5]}")
print(f"K55 코드 샘플 (DB에 없음): {list(k55_values - db_funds)[:5]}")

# DB fund_code 형식 분포
from collections import Counter
prefixes = Counter(c[:3] for c in db_funds)
print(f"\nDB fund_code 접두어 분포: {dict(prefixes.most_common(10))}")

conn.close()
