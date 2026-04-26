import csv
from collections import Counter
from pathlib import Path


def cohen_kappa(labels_a, labels_b):
    if len(labels_a) != len(labels_b) or not labels_a:
        raise ValueError("Label lists must have same non-zero length.")

    n = len(labels_a)
    observed = sum(1 for a, b in zip(labels_a, labels_b) if a == b) / n
    pa = Counter(labels_a)
    pb = Counter(labels_b)
    classes = set(pa) | set(pb)
    expected = sum((pa[c] / n) * (pb[c] / n) for c in classes)

    if expected == 1.0:
        return 1.0
    return (observed - expected) / (1 - expected)


def main():
    input_csv = Path(__file__).with_name("dual_annotations_sample.csv")
    rows = list(csv.DictReader(input_csv.open("r", encoding="utf-8")))

    should_refuse_a = [row["annotator_a_should_refuse"] for row in rows]
    should_refuse_b = [row["annotator_b_should_refuse"] for row in rows]
    risk_a = [row["annotator_a_risk_label"] for row in rows]
    risk_b = [row["annotator_b_risk_label"] for row in rows]

    print(f"should_refuse Cohen's kappa: {cohen_kappa(should_refuse_a, should_refuse_b):.4f}")
    print(f"risk_label Cohen's kappa:    {cohen_kappa(risk_a, risk_b):.4f}")


if __name__ == "__main__":
    main()
