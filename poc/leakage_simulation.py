"""Step B: Monte Carlo simulation of supplier data leakage.

Answers: "for 10,000 events processed by my suppliers, how sure am I that
no real PII actually gets exposed?"

Two exposure surfaces come out of Step A (poc/sql_minimize.py):
  - ai_view:           the minimized view sent to an AI/routing vendor.
                        With minimization, it contains zero structured PII.
                        Without it, it would carry the full raw record.
  - encrypted_at_rest: the base table (backups, subcontracted support
                        desk). PII columns are stored encrypted; they only
                        become real PII if a leak AND a key compromise
                        both occur.

Two independent modeling assumptions are simulated, because assuming pure
per-event independence understates real breach risk:
  - iid:    each event is leaked independently at random (misconfiguration,
            one-off human error).
  - breach: a single incident exposes a whole batch of events at once
            (the dominant real-world pattern for actual breaches).

A residual risk is always kept even with perfect minimization: free-text
fields (issue_description) can incidentally contain PII a user typed in,
independent of which structured columns were dropped.

Usage:
    python poc/leakage_simulation.py [--events 10000] [--repetitions 2000] [--threshold 0.01]
"""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
from pathlib import Path
from typing import Dict, List

SUPPLIERS_PATH = Path(__file__).parent / "data" / "suppliers.json"

# Residual risk that survives even a perfectly minimized, correctly
# encrypted pipeline -- documented assumptions, not derived values.
RESIDUAL_FREE_TEXT_PII_RATE = 0.02     # share of tickets whose free text itself carries incidental PII
MIN_CRYPTO_RESIDUAL_RISK = 1e-6        # floor risk of a crypto/implementation flaw, independent of key compromise


def load_suppliers() -> List[Dict]:
    with open(SUPPLIERS_PATH, encoding="utf-8") as f:
        return json.load(f)


def exposure_given_leak(supplier: Dict, minimized: bool) -> float:
    """P(a leaked record carries real, usable PII | a leak occurred)."""
    if supplier["surface"] == "ai_view":
        p_struct = 0.0 if minimized else 1.0
    else:  # encrypted_at_rest: Step A minimization doesn't change this surface
        key_p = supplier.get("key_compromise_probability_given_leak", 0.0)
        p_struct = key_p + (1 - key_p) * MIN_CRYPTO_RESIDUAL_RISK
    p_freetext = RESIDUAL_FREE_TEXT_PII_RATE
    return 1 - (1 - p_struct) * (1 - p_freetext)


def sample_poisson(lam: float, rng: random.Random) -> int:
    """Poisson sample; a good Binomial(N, p) approximation for small p, large N."""
    if lam <= 0:
        return 0
    if lam < 30:
        threshold = math.exp(-lam)
        k, p = 0, 1.0
        while True:
            k += 1
            p *= rng.random()
            if p <= threshold:
                return k - 1
    return max(0, round(rng.gauss(lam, math.sqrt(lam))))


def simulate_iid(events: int, suppliers: List[Dict], minimized: bool, rng: random.Random) -> int:
    p_event_safe = 1.0
    for s in suppliers:
        p_exposure = s["leak_probability_per_event"] * exposure_given_leak(s, minimized)
        p_event_safe *= (1 - p_exposure)
    p_event_unsafe = 1 - p_event_safe
    return sample_poisson(events * p_event_unsafe, rng)


def simulate_breach(events: int, suppliers: List[Dict], minimized: bool, rng: random.Random) -> int:
    breaching = [s for s in suppliers if rng.random() < s.get("breach_probability_per_batch", 0.0)]
    if not breaching:
        return 0
    p_record_safe = 1.0
    for s in breaching:
        p_record_safe *= (1 - exposure_given_leak(s, minimized))
    return sample_poisson(events * (1 - p_record_safe), rng)


def run_monte_carlo(events: int, repetitions: int, suppliers: List[Dict], mode: str, minimized: bool, seed: int) -> List[int]:
    rng = random.Random(seed)
    sim = simulate_iid if mode == "iid" else simulate_breach
    return [sim(events, suppliers, minimized, rng) for _ in range(repetitions)]


def summarize(results: List[int], events: int, threshold: float) -> Dict:
    results_sorted = sorted(results)
    p_any = sum(r > 0 for r in results) / len(results)
    return {
        "repetitions": len(results),
        "events_per_batch": events,
        "prob_any_real_pii_exposure": p_any,
        "expected_exposed_events": statistics.mean(results),
        "p95_exposed_events": results_sorted[int(0.95 * (len(results) - 1))],
        "p99_exposed_events": results_sorted[int(0.99 * (len(results) - 1))],
        "max_exposed_events": max(results),
        "safe": p_any <= threshold,
        "threshold": threshold,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=int, default=10_000)
    parser.add_argument("--repetitions", type=int, default=2000)
    parser.add_argument("--threshold", type=float, default=0.01,
                         help="Max acceptable probability of >=1 real PII exposure per batch")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default=str(Path(__file__).parent / "leakage_report.json"))
    args = parser.parse_args()

    suppliers = load_suppliers()
    report = {"events": args.events, "repetitions": args.repetitions, "threshold": args.threshold, "scenarios": {}}

    print(f"Simulating {args.repetitions} repetitions of {args.events} supplier-processed events each\n")
    for mode in ("iid", "breach"):
        for minimized, label in ((True, "with_step_a_minimization"), (False, "without_step_a_minimization")):
            results = run_monte_carlo(args.events, args.repetitions, suppliers, mode, minimized, args.seed)
            summary = summarize(results, args.events, args.threshold)
            report["scenarios"].setdefault(mode, {})[label] = summary

            print(f"[{mode}] {label}:")
            print(f"  P(>=1 real PII exposure in {args.events} events): {summary['prob_any_real_pii_exposure']:.2%}")
            print(f"  Expected exposed events: {summary['expected_exposed_events']:.3f} "
                  f"(p95={summary['p95_exposed_events']}, p99={summary['p99_exposed_events']}, max={summary['max_exposed_events']})")
            print(f"  Safe (threshold {args.threshold:.0%})? {'YES' if summary['safe'] else 'NO'}\n")

    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Full report written to {args.out}")

    print("\nBottom line:")
    for mode in ("iid", "breach"):
        with_min = report["scenarios"][mode]["with_step_a_minimization"]
        without_min = report["scenarios"][mode]["without_step_a_minimization"]
        delta_p = without_min["prob_any_real_pii_exposure"] - with_min["prob_any_real_pii_exposure"]
        delta_volume = without_min["expected_exposed_events"] - with_min["expected_exposed_events"]
        print(f"  [{mode}] Step A minimization cuts P(any real PII exposure) by "
              f"{delta_p:.2%} (from {without_min['prob_any_real_pii_exposure']:.2%} to {with_min['prob_any_real_pii_exposure']:.2%}) "
              f"and cuts expected exposed events by {delta_volume:.1f} "
              f"(from {without_min['expected_exposed_events']:.1f} to {with_min['expected_exposed_events']:.1f}) -- "
              f"the residual risk that remains either way is the free-text channel, not structured PII columns.")
        if not with_min["safe"]:
            print(f"  [{mode}] Still NOT safe at the {args.threshold:.0%} threshold even with minimization -- "
                  f"reduce supplier leak/breach probabilities or key-compromise risk in {SUPPLIERS_PATH.name}, "
                  f"or lower RESIDUAL_FREE_TEXT_PII_RATE by scrubbing free-text fields before they leave the system.")


if __name__ == "__main__":
    main()
