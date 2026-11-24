from surfaceqa.freeview import freeview_command

S = "/data/fs/sub-01"
SURFACES = (f"-f {S}/surf/lh.white:edgecolor=blue {S}/surf/lh.pial:edgecolor=yellow "
            f"{S}/surf/rh.white:edgecolor=red {S}/surf/rh.pial:edgecolor=yellow")


def test_command_opens_the_t1_the_file_to_edit_and_the_surfaces_at_the_mark():
    assert freeview_command(S, "mri/brain.finalsurfs.manedit.mgz", [1.5, -20.0, 3.254]) == (
        f"freeview -v {S}/mri/orig.mgz {S}/mri/brain.finalsurfs.manedit.mgz {SURFACES} "
        "-ras 1.50 -20.00 3.25 tkreg -cc -viewport coronal")


def test_overlay_file_is_drawn_translucent():
    command = freeview_command(S, "mri/wm.mgz", [0, 0, 0], overlay=True)
    assert f"{S}/mri/wm.mgz:colormap=heat:opacity=0.4 -f" in command


def test_no_coordinate_means_no_cursor_option():
    for tkr in (None, [1.0, 2.0], [1.0, "a", 2.0], [1.0, float("nan"), 2.0]):
        command = freeview_command(S, "mri/wm.mgz", tkr)
        assert "-ras" not in command and "-cc" not in command
        assert command.endswith("-viewport coronal")


def test_no_file_to_edit_opens_the_t1_alone():
    assert freeview_command(S, None, None).startswith(f"freeview -v {S}/mri/orig.mgz -f ")


def test_paths_with_spaces_and_shell_characters_are_quoted():
    command = freeview_command("/data/my scans/sub 01; rm -rf x", "mri/wm.mgz", None)
    assert "'/data/my scans/sub 01; rm -rf x/mri/orig.mgz'" in command
    assert "'/data/my scans/sub 01; rm -rf x/surf/lh.pial':edgecolor=yellow" in command
    assert "sub 01; rm -rf x/mri/wm.mgz'" in command
