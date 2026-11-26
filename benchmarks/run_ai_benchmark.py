"""Benchmark runner for Hỏa Lò AI Engine (Vietnamese-Pivot RAG + dataset_hoa_lo_vi).

Measures real deterministic performance across:
1. 1,600 indexed visitor questions (Bo1 VI, Bo2 VI, 4-Lang EN/ES/ZH/JA)
2. 95-case Groq Eval Suite (groq_eval_suite.jsonl)
3. 30 Audit hard regression cases from dataset_hoa_lo_vi (mau_test_ca_kho_audit.json)
Outputs benchmarks/ai_benchmark_report.json.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from ai_engine import HybridHoaLoRetriever  # noqa: E402


def main() -> None:
    ret = HybridHoaLoRetriever()
    kb_dir = ROOT_DIR / "ai_engine" / "knowledge"

    # 1. Benchmark 1,600 Multilingual Questions
    by_ds: dict[str, dict[str, int]] = {}
    t0 = time.perf_counter()
    for item in ret.extended_q:
        ds = item["dataset"]
        st = by_ds.setdefault(ds, {"total": 0, "zone_ok": 0, "false_oos": 0})
        st["total"] += 1
        ctx = ret.retrieve(item["question"], language="auto")
        if ctx["zone_id"] == item["zone_id"]:
            st["zone_ok"] += 1
        if ctx["is_likely_out_of_scope"]:
            st["false_oos"] += 1
    elapsed_1600 = time.perf_counter() - t0

    # 2. Check 95-case groq_eval_suite.jsonl
    eval_rows = [
        json.loads(line)
        for line in (kb_dir / "groq_eval_suite.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    in_scope_total = sum(1 for r in eval_rows if not r["expected_out_of_scope"])
    oos_total = len(eval_rows) - in_scope_total
    ev_ok = 0
    ev_oos_ok = 0
    for row in eval_rows:
        ctx = ret.retrieve(row["question"], language=row["language"])
        if row["expected_out_of_scope"]:
            if ctx["is_likely_out_of_scope"]:
                ev_oos_ok += 1
        elif ctx["zone_id"] == row["expected_zone_id"] and not ctx["is_likely_out_of_scope"]:
            ev_ok += 1

    # 3. Check 30 hard audit regression cases from dataset_hoa_lo_vi
    enrich = json.loads((kb_dir / "hoa_lo_vi_enrichments.json").read_text(encoding="utf-8"))
    hard_cases = enrich.get("hard_audit_cases", [])
    hard_passed = 0
    for hc in hard_cases:
        q = hc.get("question", "")
        if not q:
            continue
        ctx = ret.retrieve(q, language="vi")
        expected_z = hc.get("zone_id") or hc.get("expected_zone_id")
        if not ctx["is_likely_out_of_scope"] and (not expected_z or ctx["zone_id"] == expected_z):
            hard_passed += 1

    total_ok = sum(v["zone_ok"] for v in by_ds.values())
    total_q = sum(v["total"] for v in by_ds.values())
    false_oos_total = sum(v["false_oos"] for v in by_ds.values())

    report = {
        "engine": "HoaLoGroqSkill Vietnamese-Pivot v2.2 + dataset_hoa_lo_vi",
        "kb_totals": {
            "zones": len(ret.zones),
            "golden_qa": len(ret.golden_qa),
            "fact_cards": len(ret.fact_cards),
            "micro_stories": len(ret.micro_stories),
            "myth_busters": len(ret.myth_busters),
            "disambiguation_rules": len(ret.disambiguation_rules),
            "extended_questions": len(ret.extended_q),
        },
        "benchmark_1600": {
            "total": total_q,
            "zone_accuracy_count": total_ok,
            "zone_accuracy_pct": round(100.0 * total_ok / max(1, total_q), 2),
            "false_oos_count": false_oos_total,
            "elapsed_sec": round(elapsed_1600, 2),
            "avg_ms_per_query": round(elapsed_1600 * 1000.0 / max(1, total_q), 2),
            "by_dataset": by_ds,
        },
        "eval_suite_95": {
            "in_scope_passed": ev_ok,
            "in_scope_total": in_scope_total,
            "oos_passed": ev_oos_ok,
            "oos_total": oos_total,
        },
        "hard_audit_cases": {
            "passed": hard_passed,
            "total": len(hard_cases),
        },
    }

    out_path = ROOT_DIR / "benchmarks" / "ai_benchmark_report.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
