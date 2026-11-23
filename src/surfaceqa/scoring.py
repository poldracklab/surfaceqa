"""The suspicion score: orders subjects and locations for review, nothing more."""

from surfaceqa.findings import Finding

WEIGHT = {"pial_out": 1.0, "gray_missed": 1.0, "white_short": 1.0, "crossing": 2.0,
          "thickness": 0.5, "topology": 0.2}  # thickness repeats volume findings; defects are mostly routine
UNIT = 100.0  # mm^3, or vertices, per point
CAP = 10.0  # one huge finding should not drown the rest


def finding_points(finding: Finding) -> float:
    amount = finding.size_mm3 if finding.size_mm3 is not None else finding.n
    return min(amount / UNIT, CAP) * WEIGHT[finding.kind]


def suspicion_score(findings: list[Finding]) -> float:
    return round(sum(finding_points(f) for f in findings), 1)


def rank_within_pipeline(scores: dict[str, tuple[str, float]]) -> dict[str, dict]:
    """key -> {"rank", "of"}; highest score is rank 1 and ties share the lower number."""
    ranks = {}
    for pipeline in {p for p, _ in scores.values()}:
        group = {key: score for key, (p, score) in scores.items() if p == pipeline}
        for key, score in group.items():
            higher = sum(other > score for other in group.values())
            ranks[key] = {"rank": higher + 1, "of": len(group)}
    return ranks
