from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
requirements_file = ROOT / "docs" / "requirements" / "requirements.csv"
with requirements_file.open("r", encoding="utf-8-sig", newline="") as handle:
    rows = list(csv.DictReader(handle))

print(f"Requirements registered: {len(rows)}")
for status in sorted({row["status"] for row in rows}):
    print(f"  {status}: {sum(row['status'] == status for row in rows)}")
print("Phase 00 gate: see docs/phase-gates/PHASE-00-EXIT.md")
