from surfaceqa.invocation import original_command, rerun_commands
from tests.synth import (FASTSURFER_COMMAND, FREESURFER_COMMAND, fastsurfer_log, recon_all_log,
                         write_subject)

FAST = ("/fastsurfer/run_fastsurfer.sh --fs_license /fastsurfer/my_mri_data/license.txt "
        "--t1 /fastsurfer/my_mri_data/anat_avg/sub-07_T1w_avg.nii.gz --sid sub-07 --sd /outputs "
        "--3T --threads 8")
FREE = ("/usr/local/freesurfer/8.2.0/bin/recon-all -subjid sub-07 -i a.nii.gz -i b.nii.gz "
        "-T2 t2.mgz -T2pial -3T -all -parallel -openmp 8")


def test_fastsurfer_reruns_add_edits_and_surf_only():
    runs = rerun_commands("fastsurfer", FAST, "sub-07")
    assert runs == {"seg": FAST + " --edits", "surf": FAST + " --edits --surf_only"}


def test_fastsurfer_flags_are_never_added_twice():
    runs = rerun_commands("fastsurfer", FAST + " --edits --surf_only", "sub-07")
    assert runs["seg"].count("--edits") == 1 and "--surf_only" not in runs["seg"]
    assert runs["surf"].count("--edits") == 1 and runs["surf"].count("--surf_only") == 1
    assert "--t1 /fastsurfer/my_mri_data/anat_avg/sub-07_T1w_avg.nii.gz" in runs["seg"]


def test_recon_all_reruns_keep_the_options_and_drop_the_inputs():
    runs = rerun_commands("freesurfer", FREE, "sub-07")
    tail = "-T2pial -3T -parallel -openmp 8"
    assert runs == {
        "pial": f"recon-all -s sub-07 -autorecon-pial {tail}",
        "wm": f"recon-all -s sub-07 -autorecon2-wm -autorecon3 {tail}",
        "cp": f"recon-all -s sub-07 -autorecon2-cp -autorecon3 {tail}",
    }


def test_recon_all_rerun_uses_the_stored_expert_options_and_keeps_the_subjects_folder():
    command = "recon-all -s x -sd /data/subjects -i a.nii -FLAIR f.nii -FLAIRpial -expert opts.txt -autorecon1 -autorecon2 -hires"
    assert rerun_commands("freesurfer", command, "x")["pial"] == (
        "recon-all -s x -autorecon-pial -sd /data/subjects -FLAIRpial -xopts-use -hires")


def test_a_name_with_shell_characters_is_quoted():
    assert "-s 'sub 07; rm'" in rerun_commands("freesurfer", FREE, "sub 07; rm")["pial"]
    quoted = rerun_commands("fastsurfer", "run.sh --t1 '/data/my scans/t1.nii' --sid a", "a")["seg"]
    assert "'/data/my scans/t1.nii'" in quoted


def test_without_a_command_a_template_with_placeholders_is_shown():
    fast = rerun_commands("fastsurfer", None, "sub-07")
    free = rerun_commands("freesurfer", None, "sub-07")
    assert set(fast) == {"seg", "surf"} and set(free) == {"pial", "wm", "cp"}
    assert all("<" in command for command in [*fast.values(), *free.values()])
    assert fast["surf"].endswith("--edits --surf_only") and "--surf_only" not in fast["seg"]
    assert "-s sub-07 -autorecon2-wm -autorecon3" in free["wm"]


def test_an_unusable_command_line_falls_back_to_the_template():
    assert "<" in rerun_commands("fastsurfer", "run.sh --t1 'unclosed", "a")["seg"]
    assert "<" in rerun_commands("fastsurfer", "   ", "a")["seg"]


def test_the_launch_template_wraps_every_command():
    runs = rerun_commands("fastsurfer", FAST, "sub-07", "docker run --gpus all img {command}")
    assert runs["seg"] == f"docker run --gpus all img {FAST} --edits"
    assert runs["surf"].startswith("docker run --gpus all img /fastsurfer/run_fastsurfer.sh")


def test_unknown_pipeline_has_no_rerun_commands():
    assert rerun_commands("unknown", None, "a") == {}


def test_original_command_is_read_from_the_logs(tmp_path):
    fast = write_subject(tmp_path / "fastsurfer")
    free = write_subject(tmp_path / "freesurfer", pipeline="freesurfer")
    assert original_command(fast, "fastsurfer") == FASTSURFER_COMMAND
    assert original_command(free, "freesurfer") == FREESURFER_COMMAND


def test_original_command_missing(tmp_path):
    fast = write_subject(tmp_path / "fastsurfer", command=None)
    free = write_subject(tmp_path / "freesurfer", pipeline="freesurfer", command=None)
    assert original_command(fast, "fastsurfer") is None
    assert original_command(free, "freesurfer") is None
    (fast / "scripts" / "deep-seg.log").unlink()
    assert original_command(fast, "fastsurfer") is None
    assert original_command(fast, "unknown") is None


def test_the_first_invocation_is_the_original(tmp_path):
    fast = write_subject(tmp_path / "fastsurfer")
    (fast / "scripts" / "deep-seg.log").write_text(
        fastsurfer_log("run.sh --sid a") + fastsurfer_log("run.sh --sid a --edits"))
    free = write_subject(tmp_path / "freesurfer", pipeline="freesurfer")
    (free / "scripts" / "recon-all.log").write_text(
        recon_all_log("/fs/bin/recon-all -s a -all") + recon_all_log("/fs/bin/recon-all -s a -autorecon-pial"))
    assert original_command(fast, "fastsurfer") == "run.sh --sid a"
    assert original_command(free, "freesurfer") == "/fs/bin/recon-all -s a -all"
