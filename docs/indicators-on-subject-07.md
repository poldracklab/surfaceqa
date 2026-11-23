# Indicators on NSD subject 07

Date: 2026-11-23. Three reconstructions of the same person:

- `fastsurfer/sub-07`: FastSurfer 2.6.1, 0.8 mm
- `freesurfer-8.2.0/sub-07`: recon-all 8.2.0, 1 mm, with a T2
- `freesurfer-NSD/subj07`: FreeSurfer 6.0, 0.8 mm, manually edited by the NSD team

**This is not validation.** It is one person, nobody with expertise in judging surfaces
rated anything, and the judgments below are the builder's reading of close-up images of
the top-ranked findings. It says which indicators produce output worth a reviewer's
attention on this data and which do not. Whether they find the errors that matter can
only be answered by the ratings collected in stage 3.

## What fired

Count of findings, with total size (mm³ for volume indicators, vertices for the two
surface indicators). "not run" means the inputs do not exist for that pipeline.

| Indicator | FastSurfer 2.6.1 | recon-all 8.2.0 | NSD FreeSurfer 6 |
|---|---|---|---|
| `ribbon_outside_brain` | 3 (106 mm³) | 0 | 6 (2,877 mm³) |
| `ribbon_in_nonbrain_mask` | not run | 0 | not run |
| `ribbon_in_cerebellum` | 0 | 0 | 1 (35 mm³) |
| `missed_gray` | 4 (146 mm³) | not run | not run |
| `white_matter_in_ribbon` | 0 | 12 (604 mm³) | 50 listed + 21 not listed (5,356 mm³) |
| `bright_ribbon` | 0 | 0 | 0 |
| `hemisphere_crossing` | 0 | 0 | 0 |
| `thick_patches` | 6 (433 vertices) | 5 (614 vertices) | 4 (360 vertices) |
| `topology_defects` | 2 (794 vertices) | 7 (3,196 vertices) | 13 (3,932 vertices) |
| **Suspicion score** | **6.3** | **15.5** | **83.1** |

Scores are not comparable across pipelines: the indicators compare the surfaces with a
different segmentation in each.

## What the top findings look like

Read from close-ups (48 to 56 mm fields, all three planes) of the 18 highest-ranked
findings per reconstruction.

**FastSurfer**

- `ribbon_outside_brain`, 62 mm³, filed under "sinus": the pial surface at the bottom of
  a medial occipital gyrus, next to the tentorium, encloses medium-gray tissue that the
  deep-learning segmentation calls background. This looks like the kind of error Kay
  describes (pial extending toward the sinus where it hooks under the brain). Small.
  **Plausibly real.**
- `missed_gray`, 54 mm³, medial temporal: next to the midline near the hippocampus. Kay
  calls this region ambiguous; so is this. **Cannot tell.**
- `thick_patches` (6): the two examined are in the insula, where cortex over the claustrum
  commonly measures thick. **Likely anatomy, not error.**
- `topology_defects` (2): both on the medial wall next to the lateral ventricle, a
  non-cortical part of the surface. **Routine.**

**recon-all 8.2.0**

- `topology_defects` (7): the largest is on the medial wall; three are inside occipital
  and frontal gyri. All were repaired automatically. **Routine, but they were the five
  top-ranked findings.**
- `white_matter_in_ribbon` (12): thin strips deep in sulci where the atlas-based
  `aseg.presurf` says white matter and the ribbon says cortex. At 1 mm the atlas labels
  are coarser than the surfaces. **Probably the segmentation, not the surface.**
- Nothing fired for the pial surface at all.

**NSD FreeSurfer 6 (manually edited)**

- `ribbon_outside_brain`, 1,921 mm³: orbitofrontal cortex on both sides (gyrus rectus
  and medial orbital gyri). In the images the ribbon there is a gray band between the
  white and pial contours, i.e. it looks like real cortex that the edited surfaces
  include and that FreeSurfer 6's `aseg.presurf` labels as background. **The surface
  looks right and the segmentation wrong.**
- `ribbon_outside_brain`, 782 mm³: temporal pole, same pattern. **Same reading.**
- `white_matter_in_ribbon` (71): as for recon-all 8.2. **Probably the segmentation.**

The NSD reconstruction scores highest of the three, and the reading above is that most
of that score is the old segmentation disagreeing with surfaces that were corrected by
hand. A high score means "the surfaces and the segmentation disagree here", which is a
reason to look and nothing more.

## Against what Kay names in the video

| Error he names | Did an indicator fire there? |
|---|---|
| Pial into the sagittal sinus, posterior slices | No, in any reconstruction. One small FastSurfer finding at the tentorium is the nearest thing. |
| Pial into the transverse sinus / under the occipital lobe | FastSurfer: one finding (62 mm³). recon-all: none. |
| Cortex / cerebellum interface | NSD: one small finding (35 mm³). Others: none. He also found this region mostly fine. |
| Inferior frontal membrane included | No. |
| Orbitofrontal gray matter missed | FastSurfer: three small `missed_gray` findings in the orbitofrontal region. recon-all: cannot be computed. |
| Ear-canal dropout, gray missed | FastSurfer: one finding filed under inferior temporal. recon-all: cannot be computed. |
| White surface short of gyral crowns | `white_matter_in_ribbon` fires in the recon-all reconstructions, but looks like segmentation coarseness. |
| Hemispheres crossing | No. The overlap exists (41 to 183 voxels) but is scattered below the 20 mm³ cluster minimum. |

Two lists that matter:

**Mostly noise on this subject**

- `topology_defects`: routine, automatically repaired, often on the medial wall.
- `thick_patches`: the ones examined are insula.
- `white_matter_in_ribbon` against recon-all's atlas segmentation.
- `ribbon_outside_brain` against FreeSurfer 6's `aseg.presurf`.

**Named by Kay and not caught**

- Pial into the sagittal sinus. Whether this error is present in these reconstructions
  was not established: posterior coronal slices of the recon-all 8.2 reconstruction show
  a few small pial bulges near the occipital pole that no indicator flagged, and the
  builder cannot say from the images whether they are sinus or cortex.
- The inferior frontal membrane.
- Hemisphere crossing, because of the cluster minimum.
- Every pial error in recon-all output. For recon-all the only segmentation to compare
  against is the one recon-all itself used, so agreement is close to guaranteed
  (3 voxels of ribbon over background). The sinus and dura label files that recon-all 8.2
  writes overlap the ribbon by 2 and 14 voxels here, below the minimum.
- `bright_ribbon` found nothing anywhere. Either the threshold (median + 4 scaled MADs)
  is too strict or bright tissue inside the ribbon is not how these errors show up.

## Changes made because of this

- **Topology weight lowered from 0.5 to 0.2** in the score. Routine defects were the
  top-ranked findings in two of three reconstructions.
- **Medial orbitofrontal findings go to "Inferior frontal and orbitofrontal"**, not
  "Frontal midline". The largest NSD finding is on the orbital surface and was being filed
  under the midline.
- **No threshold was changed.** One subject is not grounds for tuning `MARGIN_MM`,
  `MIN_CLUSTER_MM3` or `BRIGHT_MAD`, and the misses above are mostly not threshold
  problems.

## What this suggests for later stages

- For FastSurfer output the indicators point at plausible places. For recon-all output
  they currently say little about the pial surface, which is where most of the errors Kay
  describes are. The reviewer's eyes, the fixed default locations per region, and the
  cohort thickness comparison planned for stage 5 carry more of the weight there.
- A segmentation independent of recon-all would make the recon-all indicators
  meaningful. Running FastSurfer's segmentation step alone on recon-all subjects is one
  way; it is not part of the current design.
- The crossing indicator should probably ignore the cluster minimum, or use a smaller
  one. Left unchanged until ratings say whether those scattered voxels matter.

## Cost

Building the three reconstructions with indicators takes about 63 s with three parallel
jobs (about 44 s for five subject folders without them). Each run folder grows by well
under 1 MB (`findings.json` plus the voxel list).
