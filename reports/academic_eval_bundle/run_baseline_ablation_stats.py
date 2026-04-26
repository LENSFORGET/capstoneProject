import csv
import json
import math
import random
from collections import defaultdict
from statistics import mean
from pathlib import Path

INPUT_CSV = Path(__file__).with_name("baseline_ablation_runs_pilot.csv")
OUTPUT_CSV = Path(__file__).with_name("significance_tests.csv")
OUTPUT_META = Path(__file__).with_name("run_metadata.json")
METRIC = "overall_score"
BASELINE = "B0"
BOOTSTRAP_B = 1000
PERMUTATION_B = 5000
RANDOM_SEED = 20260424


def read_rows(path: Path):
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def bootstrap_ci(values, b=1000, alpha=0.05):
    rnd = random.Random(RANDOM_SEED)
    n = len(values)
    samples = []
    for _ in range(b):
        resample = [values[rnd.randrange(0, n)] for _ in range(n)]
        samples.append(mean(resample))
    samples.sort()
    lower_idx = int((alpha / 2) * (b - 1))
    upper_idx = int((1 - alpha / 2) * (b - 1))
    return samples[lower_idx], samples[upper_idx]


def paired_permutation_pvalue(base_vals, cand_vals, b=5000):
    rnd = random.Random(RANDOM_SEED)
    diffs = [c - a for a, c in zip(base_vals, cand_vals)]
    observed = abs(mean(diffs))
    count = 0
    for _ in range(b):
        signed = [(d * (-1 if rnd.random() < 0.5 else 1)) for d in diffs]
        if abs(mean(signed)) >= observed:
            count += 1
    return (count + 1) / (b + 1)


def effect_size_cohens_d(base_vals, cand_vals):
    diffs = [c - a for a, c in zip(base_vals, cand_vals)]
    mu = mean(diffs)
    var = sum((x - mu) ** 2 for x in diffs) / max(1, len(diffs) - 1)
    std = math.sqrt(var)
    return 0.0 if std == 0 else mu / std


def main():
    rows = read_rows(INPUT_CSV)
    by_variant = defaultdict(list)
    for row in rows:
        by_variant[row["variant"]].append(row)
    for variant in by_variant:
        by_variant[variant] = sorted(by_variant[variant], key=lambda x: int(x["seed"]))

    base_vals = [float(r[METRIC]) for r in by_variant[BASELINE]]
    base_mean = mean(base_vals)

    out = []
    for variant, vrows in by_variant.items():
        vals = [float(r[METRIC]) for r in vrows]
        ci_low, ci_high = bootstrap_ci(vals, b=BOOTSTRAP_B)
        row = {
            "variant": variant,
            "metric": METRIC,
            "mean": round(mean(vals), 6),
            "ci95_low": round(ci_low, 6),
            "ci95_high": round(ci_high, 6),
            "delta_vs_baseline": round(mean(vals) - base_mean, 6),
            "p_value_vs_baseline": "",
            "effect_size_d": "",
            "significant_0_05": "",
        }
        if variant != BASELINE:
            p = paired_permutation_pvalue(base_vals, vals, b=PERMUTATION_B)
            d = effect_size_cohens_d(base_vals, vals)
            row["p_value_vs_baseline"] = round(p, 6)
            row["effect_size_d"] = round(d, 6)
            row["significant_0_05"] = "yes" if p < 0.05 else "no"
        out.append(row)

    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)

    metadata = {
        "input_csv": str(INPUT_CSV.name),
        "baseline": BASELINE,
        "metric": METRIC,
        "bootstrap_b": BOOTSTRAP_B,
        "permutation_b": PERMUTATION_B,
        "random_seed": RANDOM_SEED,
        "note": "pilot run in consolidated single-folder bundle",
    }
    with OUTPUT_META.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    print(f"Created: {OUTPUT_CSV}")
    print(f"Created: {OUTPUT_META}")


if __name__ == "__main__":
    main()
