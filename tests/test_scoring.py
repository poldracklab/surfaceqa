from surfaceqa.findings import Finding
from surfaceqa.scoring import finding_points, rank_within_pipeline, suspicion_score


def test_points():
    assert finding_points(Finding("x", "pial_out", (0, 0, 0), 250.0, 500)) == 2.5
    assert finding_points(Finding("x", "pial_out", (0, 0, 0), 5000.0, 9000)) == 10.0  # capped
    assert finding_points(Finding("x", "crossing", (0, 0, 0), 100.0, 100)) == 2.0
    assert finding_points(Finding("x", "thickness", (0, 0, 0), None, 300)) == 1.5


def test_topology_defects_weigh_little():
    # On subject 07 the largest defects sit on the medial wall and were repaired automatically,
    # yet they were the top-ranked findings in two of three reconstructions.
    assert finding_points(Finding("x", "topology", (0, 0, 0), None, 500)) == 1.0


def test_score_is_the_rounded_sum():
    fs = [Finding("x", "pial_out", (0, 0, 0), 123.0, 1), Finding("x", "pial_out", (0, 0, 0), 20.0, 1)]
    assert suspicion_score(fs) == 1.4 and suspicion_score([]) == 0.0


def test_rank_within_pipeline():
    ranks = rank_within_pipeline({"a": ("fastsurfer", 5.0), "b": ("fastsurfer", 9.0),
                                  "c": ("freesurfer", 1.0), "d": ("fastsurfer", 5.0)})
    assert ranks["b"] == {"rank": 1, "of": 3} and ranks["a"]["rank"] == 2 and ranks["d"]["rank"] == 2
    assert ranks["c"] == {"rank": 1, "of": 1}


def test_places_to_look_do_not_count_towards_the_score():
    hint = Finding("x", "look_here", (0, 0, 0), 900.0, 900)
    assert finding_points(hint) == 0.0
    assert suspicion_score([hint, Finding("x", "pial_out", (0, 0, 0), 100.0, 1)]) == 1.0
