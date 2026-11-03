"""ROIC per operating unit and service efficiency by month, under a demonstrative season pattern.

Standard library only, so it runs on Vercel and locally. All inputs are synthetic (data/seasonality/).

Per unit and month:
  activity      = 1 + sensitivity x (season index - 1)
  revenue       = revenue at index 1 x activity
  EBIT          = revenue x (1 - variable cost %) - fixed cost        (crews and plant cost money in quiet months too)
  NOPAT         = EBIT x (1 - 30% tax)
  invested cap. = plant capital + working capital (months of revenue tied up in WIP and debtors)
  ROIC (ann.)   = NOPAT x 12 / invested capital
Service efficiency (per unit, revenue-weighted for the business):
  utilisation   = billable share of paid crew hours, capped at 95%
  on-time       = jobs completed by the agreed date; falls when crews are stretched above an index of 1.0
"""

from __future__ import annotations

import csv
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "seasonality"
TAX = 0.30


def _read(name: str) -> list[dict[str, str]]:
    with (DATA / name).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def run() -> dict:
    profile = _read("season_profile.csv")
    units = _read("units.csv")
    monthly: list[dict] = []
    for u in units:
        base = float(u["revenue_at_index_1"])
        var = float(u["variable_cost_pct"])
        fixed = float(u["fixed_cost_month"])
        plant = float(u["plant_capital"])
        wc_m = float(u["working_capital_months"])
        sens = float(u["seasonal_sensitivity"])
        for p in profile:
            idx = float(p["activity_index"])
            act = 1 + sens * (idx - 1)
            rev = base * act
            ebit = rev * (1 - var) - fixed
            nopat = ebit * (1 - TAX)
            ic = plant + wc_m * rev
            util = min(0.95, 0.82 * act)
            on_time = max(0.70, min(0.97, 0.97 - 0.45 * max(0.0, act - 1.0)))
            monthly.append({"unit": u["unit"], "month": p["month"], "season": p["season"], "activity_index": idx,
                            "revenue": round(rev, 2), "ebit": round(ebit, 2), "nopat": round(nopat, 2),
                            "invested_capital": round(ic, 2), "roic_annualised": round(nopat * 12 / ic, 4),
                            "utilisation": round(util, 4), "on_time": round(on_time, 4)})
    months = [p["month"] for p in profile]
    unit_names = [u["unit"] for u in units]
    annual = []
    for name in unit_names:
        rows = [m for m in monthly if m["unit"] == name]
        nopat = sum(r["nopat"] for r in rows)
        avg_ic = sum(r["invested_capital"] for r in rows) / len(rows)
        annual.append({"unit": name, "revenue": round(sum(r["revenue"] for r in rows), 2), "nopat": round(nopat, 2),
                       "avg_invested_capital": round(avg_ic, 2), "roic": round(nopat / avg_ic, 4),
                       "loss_months": sum(1 for r in rows if r["ebit"] < 0)})
    business = []
    for i, mth in enumerate(months):
        rows = [m for m in monthly if m["month"] == mth]
        rev = sum(r["revenue"] for r in rows)
        nopat = sum(r["nopat"] for r in rows)
        ic = sum(r["invested_capital"] for r in rows)
        business.append({"month": mth, "season": profile[i]["season"], "activity_index": float(profile[i]["activity_index"]),
                         "revenue": round(rev, 2), "nopat": round(nopat, 2), "roic_annualised": round(nopat * 12 / ic, 4),
                         "utilisation": round(sum(r["utilisation"] * r["revenue"] for r in rows) / rev, 4),
                         "on_time": round(sum(r["on_time"] * r["revenue"] for r in rows) / rev, 4)})
    tot_nopat = sum(a["nopat"] for a in annual)
    tot_ic = sum(a["avg_invested_capital"] for a in annual)
    return {"months": months, "units": unit_names, "profile": profile, "monthly": monthly, "annual": annual,
            "business": business, "business_roic": round(tot_nopat / tot_ic, 4)}


if __name__ == "__main__":
    r = run()
    print("Business ROIC", r["business_roic"])
    for a in r["annual"]:
        print(a)
    for b in r["business"]:
        print(b)
