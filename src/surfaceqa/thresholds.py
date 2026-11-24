"""Every tunable number used by the indicators, in one place.

These only decide what is put in front of a reviewer first. None of them decides
whether a subject is good.
"""

MARGIN_MM = 1.0  # boundary disagreement of one voxel is noise on both 0.8 and 1 mm data
MIN_CLUSTER_MM3 = 20.0  # smaller clusters are indistinguishable from noise on subject 07
BRIGHT_MAD = 4.0  # ribbon voxels brighter than median + this many scaled MADs
THICK_MM = 4.5  # FreeSurfer caps thickness at 5; about 0.4% of cortex vertices exceed 4.5
MIN_THICK_VERTICES = 50  # a patch, not isolated vertices
MIN_DEFECT_VERTICES = 100  # small topology defects are fixed automatically and are routine
MAX_FINDINGS_PER_INDICATOR = 50  # keeps the page usable; the cap is reported
NEAR_MM = 4.0  # "next to" the cerebellum or hippocampus, for region assignment
MEDIAL_MM = 6.0  # "medial": within this distance of the other hemisphere
MIN_COHORT = 30  # subjects of one source folder needed before they are compared with each other
COHORT_Z = 4.0  # thicker than the cohort median by this many robust standard deviations ...
COHORT_MIN_MM = 1.0  # ... and by at least this much, where the cohort hardly varies
MIN_COHORT_VERTICES = 50  # a patch, not isolated vertices


def as_dict() -> dict:
    return {name: value for name, value in globals().items() if name.isupper()}
