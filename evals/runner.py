from __future__ import annotations
import argparse, asyncio, json, statistics, sys, time
from collections import Counter, defaultdict
from pathlib import Path
import yaml
from evals.metrics import METRICS, is_false_approval
from evals.stubs import STUBS
from evals.trace import AgentTrace

PRICE_IN_PER_1K = 0.0025      # adjust to your deployment's actual rates
PRICE_OUT_PER_1K = 0.010


def load_cases(path: Path) -> list[dict]:
    cases = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    for c in cases:                       # metrics read tools off `expected`
        c["expected"]["_tools"] = c.get("expected_tool_calls", [])
        c["expected"]["_oracle_facts"] = (c.get("oracle") or {}).get("facts")
    return cases


async def run_agent(agent, cases: list[dict], concurrency: int,
                    repeats: int = 1) -> list[tuple[dict, AgentTrace, int]]:
    """Run every case `repeats` times. Model output is non-deterministic, so
    a single pass is one sample, not a measurement."""
    sem = asyncio.Semaphore(concurrency)

    async def one(case, run_index):
        async with sem:
            t0 = time.perf_counter()
            try:
                trace = await agent(case)
            except Exception as exc:      # a crashed agent scores zero, it does not abort the run
                trace = AgentTrace(case_id=case["id"], error=repr(exc))
            trace.latency_ms = trace.latency_ms or (time.perf_counter() - t0) * 1000
            return case, trace, run_index

    jobs = [one(c, i) for i in range(repeats) for c in cases]
    return await asyncio.gather(*jobs)


def score(results) -> dict:
    per_metric = defaultdict(list)
    per_bucket = defaultdict(list)
    confusion = Counter()
    false_approvals, latencies = [], []
    tin = tout = 0

    for case, trace, _ in results:
        exp = case["expected"]
        for m in METRICS:
            per_metric[m.name].append(m.score(trace, exp))
        per_bucket[case["bucket"]].append(
            next(m for m in METRICS if m.name == "decision_match").score(trace, exp))
        got = (trace.output or {}).get("decision", "INVALID")
        confusion[(exp["decision"], got)] += 1
        if is_false_approval(trace, exp):
            false_approvals.append(case["id"])
        latencies.append(trace.latency_ms)
        tin += trace.tokens_in
        tout += trace.tokens_out

    n = len(results)
    return {
        "n": n,
        "metrics": {k: sum(v) / len(v) for k, v in per_metric.items()},
        "buckets": {k: sum(v) / len(v) for k, v in sorted(per_bucket.items())},
        "false_approval_rate": len(false_approvals) / n,
        "false_approval_ids": false_approvals[:10],
        "confusion": confusion,
        "p50_ms": statistics.median(latencies),
        "p95_ms": sorted(latencies)[int(0.95 * (n - 1))],
        "cost_usd": (tin / 1000 * PRICE_IN_PER_1K) + (tout / 1000 * PRICE_OUT_PER_1K),
    }


def check_gates(rep: dict, spec: dict) -> list[str]:
    failures = []
    for name, floor in (spec.get("gates") or {}).items():
        if name == "false_approval_rate":
            if rep["false_approval_rate"] > floor:
                failures.append(f"false_approval_rate {rep['false_approval_rate']:.3f} > {floor}")
        elif name in rep["metrics"] and rep["metrics"][name] < floor:
            failures.append(f"{name} {rep['metrics'][name]:.3f} < {floor}")
    for bucket, floor in (spec.get("bucket_floors") or {}).items():
        if bucket in rep["buckets"] and rep["buckets"][bucket] < floor:
            failures.append(f"bucket {bucket} {rep['buckets'][bucket]:.3f} < {floor}")
    return failures


def print_report(rep: dict, failures: list[str]) -> None:
    print(f"\n{rep['n']} cases | p50 {rep['p50_ms']:.0f}ms  p95 {rep['p95_ms']:.0f}ms "
          f"| ${rep['cost_usd']:.4f} (${rep['cost_usd']/rep['n']:.5f}/claim)\n")

    print("METRIC")
    for k, v in rep["metrics"].items():
        print(f"  {k:24} {v:.3f}")
    print(f"  {'false_approval_rate':24} {rep['false_approval_rate']:.3f}"
          f"{'  <-- ' + ','.join(rep['false_approval_ids']) if rep['false_approval_ids'] else ''}")

    print("\nDECISION MATCH BY BUCKET")
    for k, v in rep["buckets"].items():
        bar = "#" * int(v * 20)
        print(f"  {k:24} {v:.3f}  {bar}")

    print("\nCONFUSION  (expected -> got)")
    for (exp, got), n in sorted(rep["confusion"].items()):
        flag = "  <-- FALSE APPROVAL" if exp == "deny" and got == "approve" else ""
        print(f"  {exp:10} -> {got:10} {n:4}{flag}")

    if failures:
        print("\nGATE FAILURES")
        for f in failures:
            print(f"  FAIL  {f}")
    else:
        print("\nall gates passed")


def print_variance(reps: list[dict]) -> None:
    """Model output is non-deterministic. A single run is one sample; this
    reports the spread so a score can be quoted honestly."""
    n = len(reps)
    print(f"\n{'=' * 62}")
    print(f"VARIANCE OVER {n} RUNS ({reps[0]['n']} cases each)\n")

    print(f"  {'METRIC':22} {'MEAN':>7} {'MIN':>7} {'MAX':>7} {'SPREAD':>7}")
    for name in reps[0]["metrics"]:
        vals = [r["metrics"][name] for r in reps]
        print(f"  {name:22} {sum(vals)/n:7.3f} {min(vals):7.3f} {max(vals):7.3f} "
              f"{max(vals)-min(vals):7.3f}")

    fa = [r["false_approval_rate"] for r in reps]
    print(f"  {'false_approval_rate':22} {sum(fa)/n:7.3f} {min(fa):7.3f} "
          f"{max(fa):7.3f} {max(fa)-min(fa):7.3f}")

    print("\nUNSTABLE BUCKETS (score differed between runs)")
    unstable = False
    for bucket in reps[0]["buckets"]:
        vals = [r["buckets"][bucket] for r in reps]
        if max(vals) - min(vals) > 0:
            unstable = True
            print(f"  {bucket:24} " + "  ".join(f"{v:.3f}" for v in vals))
    if not unstable:
        print("  none -- every bucket scored identically in all runs")

    total = sum(r["cost_usd"] for r in reps)
    print(f"\ntotal cost across {n} runs: ${total:.4f}")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", default="always_escalate", choices=list(STUBS))
    ap.add_argument("--dataset", type=Path, default=Path("evals/datasets/golden_v1.jsonl"))
    ap.add_argument("--taxonomy", type=Path, default=Path("evals/specs/taxonomy.yaml"))
    ap.add_argument("--concurrency", type=int, default=5)
    ap.add_argument("--bucket", help="run only this bucket")
    ap.add_argument("--repeats", type=int, default=1,
                    help="run the suite N times and report mean and spread")
    args = ap.parse_args()

    cases = load_cases(args.dataset)
    if args.bucket:
        cases = [c for c in cases if c["bucket"] == args.bucket]
    spec = yaml.safe_load(args.taxonomy.read_text())

    if args.repeats == 1:
        results = await run_agent(STUBS[args.agent], cases, args.concurrency)
        rep = score(results)
        failures = check_gates(rep, spec)
        print_report(rep, failures)
        return 1 if failures else 0

    reps = []
    for i in range(args.repeats):
        results = await run_agent(STUBS[args.agent], cases, args.concurrency)
        rep = score(results)
        reps.append(rep)
        print(f"run {i + 1}/{args.repeats}: decision_match "
              f"{rep['metrics']['decision_match']:.3f}")

    print_variance(reps)
    return 1 if check_gates(reps[-1], spec) else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))