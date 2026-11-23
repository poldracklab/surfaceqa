"""Kay's regions: which one a finding belongs to, and where to look when nothing fired."""

from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage

from surfaceqa import thresholds
from surfaceqa.findings import Finding
from surfaceqa.subjectdata import SubjectData

CEREBELLUM = (7, 8, 46, 47)
HIPPOCAMPUS_AMYGDALA = (17, 18, 53, 54)
LEFT_CEREBRUM, RIGHT_CEREBRUM = (2, 3), (41, 42)
MEDIAL_TEMPORAL_PARCELS = {6, 16}
SINUS_PARCELS = {5, 21, 25, 13, 10, 29, 11}
FRONTAL_MIDLINE_PARCELS = {28, 26, 2, 17}
ORBITOFRONTAL_PARCELS = {12, 14, 19}
INFERIOR_TEMPORAL_PARCELS = {9, 7, 15}
KIND_REGION = {"crossing": "crossing", "white_short": "white_surface", "topology": "white_surface"}
NO_PARC = "no aparc.DKTatlas+aseg.mgz; findings could not be assigned to regions"
BOX_PAD = 10  # voxels of padding around the labelled brain when cropping
PARCEL_NAMES = {
    5: "cuneus", 21: "pericalcarine", 13: "lingual", 7: "fusiform",
    26: "rostral anterior cingulate", 28: "superior frontal", 12: "lateral orbitofrontal",
    14: "medial orbitofrontal", 9: "inferior temporal", 16: "parahippocampal", 6: "entorhinal",
    29: "superior parietal", 24: "precentral", 35: "insula", 23: "posterior cingulate",
}


@dataclass(frozen=True)
class Region:
    id: str
    title: str
    look_for: str
    default_labels: tuple[int, ...]


REGIONS = (
    Region("sinus", "Sagittal and transverse sinus",
           "The pial surface extending into the sinus along the midline and under the occipital "
           "lobe. The sinus is medium gray and easy to mistake for cortex. Worst in the most "
           "posterior slices.", (1005, 1021)),
    Region("cerebellum", "Cortex / cerebellum interface",
           "The pial surface running into the cerebellum on the inferior side of the occipital "
           "and temporal lobes.", (1013, 1007)),
    Region("frontal_midline", "Frontal midline",
           "The two pial surfaces nearly touch here. Check that neither extends too far or "
           "crosses the midline.", (1026, 1028)),
    Region("orbitofrontal", "Inferior frontal and orbitofrontal",
           "The pial surface including the bright membrane under the frontal lobe, and "
           "orbitofrontal gray matter being missed.", (1012, 1014)),
    Region("inferior_temporal", "Inferior temporal, near the ear canal",
           "Gray matter missed by the pial surface in the signal-dropout region. Common, and "
           "often not worth fixing.", (1009,)),
    Region("medial_temporal", "Medial temporal, hippocampus",
           "Surfaces are often irregular around the hippocampus. Judge leniently; it is hard to "
           "say what is correct here.", (1016, 1006)),
    Region("outer_edge", "Outer edge of the brain",
           "Dura or other tissue just outside the brain included in the pial surface.",
           (1029, 1024)),
    Region("white_surface", "White surface",
           "The white surface cutting off the tips of gyri, or missing deep sulci.", (1024, 1035)),
    Region("crossing", "Hemispheres crossing",
           "The left and right surfaces overlapping at the midline.", (1023,)),
)


@dataclass
class RegionContext:
    """Per-subject lookups, cropped to a box around the labelled brain."""
    reason: str = ""
    start: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=int))
    parcel: np.ndarray | None = None  # nearest cortical parcel, hemisphere removed
    medial: np.ndarray | None = None
    near_cerebellum: np.ndarray | None = None
    near_hippocampus: np.ndarray | None = None

    def at(self, volume: np.ndarray, grid) -> object:
        local = np.clip(np.asarray(grid) - self.start, 0, np.array(volume.shape) - 1)
        return volume[tuple(local)]


def _brain_box(parc: np.ndarray) -> tuple[slice, ...]:
    filled = np.argwhere(parc > 0)
    low = np.maximum(filled.min(axis=0) - BOX_PAD, 0)
    high = np.minimum(filled.max(axis=0) + BOX_PAD + 1, parc.shape)
    return tuple(slice(int(a), int(b)) for a, b in zip(low, high))


def _distance_to(mask: np.ndarray, voxel_sizes) -> np.ndarray:
    if not mask.any():
        return np.full(mask.shape, np.inf)
    return ndimage.distance_transform_edt(~mask, sampling=voxel_sizes)


def _nearest_parcel(parc: np.ndarray, voxel_sizes) -> np.ndarray:
    cortical = parc >= 1000
    if not cortical.any():
        return np.zeros_like(parc)
    index = ndimage.distance_transform_edt(~cortical, sampling=voxel_sizes,
                                           return_distances=False, return_indices=True)
    return parc[tuple(index)]


def _cerebrum_masks(parc: np.ndarray, ribbon: np.ndarray | None) -> tuple[np.ndarray, np.ndarray]:
    if ribbon is not None:
        return np.isin(ribbon, LEFT_CEREBRUM), np.isin(ribbon, RIGHT_CEREBRUM)
    left = ((parc >= 1000) & (parc < 2000)) | (parc == 2)
    return left, (parc >= 2000) | (parc == 41)


def _medial(nearest: np.ndarray, parc, ribbon, voxel_sizes) -> np.ndarray:
    """Within MEDIAL_MM of the cerebrum of the hemisphere a location does not belong to."""
    left, right = _cerebrum_masks(parc, ribbon)
    to_other = np.where(nearest >= 2000, _distance_to(left, voxel_sizes),
                        _distance_to(right, voxel_sizes))
    return to_other <= thresholds.MEDIAL_MM


def build_context(data: SubjectData) -> RegionContext:
    if data.parc is None or not (data.parc > 0).any():
        return RegionContext(reason=NO_PARC)
    box = _brain_box(data.parc)
    parc = data.parc[box]
    ribbon = None if data.ribbon is None else data.ribbon[box]
    sizes = data.voxel_sizes
    nearest = _nearest_parcel(parc, sizes)
    return RegionContext(
        start=np.array([s.start for s in box]), parcel=nearest % 1000,
        medial=_medial(nearest, parc, ribbon, sizes),
        near_cerebellum=_distance_to(np.isin(parc, CEREBELLUM), sizes) <= thresholds.NEAR_MM,
        near_hippocampus=_distance_to(np.isin(parc, HIPPOCAMPUS_AMYGDALA), sizes) <= thresholds.NEAR_MM)


def _anatomical_region(grid, ctx: RegionContext) -> str:
    parcel = int(ctx.at(ctx.parcel, grid))
    medial = bool(ctx.at(ctx.medial, grid))
    if parcel in MEDIAL_TEMPORAL_PARCELS or ctx.at(ctx.near_hippocampus, grid):
        return "medial_temporal"
    if ctx.at(ctx.near_cerebellum, grid):
        return "cerebellum"
    if parcel in SINUS_PARCELS and medial:
        return "sinus"
    if parcel in FRONTAL_MIDLINE_PARCELS and medial:
        return "frontal_midline"
    if parcel in ORBITOFRONTAL_PARCELS:
        return "orbitofrontal"
    if parcel in INFERIOR_TEMPORAL_PARCELS:
        return "inferior_temporal"
    return "outer_edge"


def assign_region(finding: Finding, ctx: RegionContext) -> str:
    if finding.kind in KIND_REGION:
        return KIND_REGION[finding.kind]
    if ctx.parcel is None:
        return "outer_edge"
    return _anatomical_region(finding.grid, ctx)


def _parcel_location(parc: np.ndarray, label: int) -> list[int] | None:
    voxels = np.argwhere(parc == label)
    if len(voxels) == 0:
        return None
    nearest = voxels[np.argmin(np.linalg.norm(voxels - voxels.mean(axis=0), axis=1))]
    return [int(v) for v in nearest]


def _region_defaults(parc: np.ndarray, region: Region) -> list[dict]:
    spots = []
    for label in region.default_labels:
        for hemi, offset in (("lh", 0), ("rh", 1000)):
            grid = _parcel_location(parc, label + offset)
            if grid is not None:
                spots.append({"grid": grid, "label": f"{hemi} {PARCEL_NAMES[label % 1000]}"})
    return spots


def default_locations(data: SubjectData) -> dict[str, list[dict]]:
    """Where to look in each region when no indicator fired there."""
    if data.parc is None:
        return {}
    return {region.id: _region_defaults(data.parc, region) for region in REGIONS}
