import sqlite3
conn = sqlite3.connect(r"C:\Users\김효진\2.FinancialData\backend\fund_platform.db")

total = conn.execute("SELECT COUNT(*) FROM funds WHERE product_type='fund'").fetchone()[0]
print(f"DB fund 총 건수: {total}")

print("\n상태별:")
for row in conn.execute("SELECT status, COUNT(*) FROM funds WHERE product_type='fund' GROUP BY status ORDER BY 2 DESC").fetchall():
    print(f"  {row[0]}: {row[1]}")

print("\nfund_code 접두어 분포:")
for row in conn.execute("SELECT SUBSTR(fund_code,1,3), COUNT(*) FROM funds WHERE product_type='fund' GROUP BY 1 ORDER BY 2 DESC").fetchall():
    print(f"  {row[0]}: {row[1]}")

conn.close()
