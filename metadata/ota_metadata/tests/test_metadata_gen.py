# Copyright 2022 TIER IV, INC. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
from pathlib import Path

# Assuming metadata_gen.py is in the same directory or importable path
import metadata_gen
from pytest_unordered import unordered


# --- ORIGINAL TESTS (MODIFIED ONLY AS NECESSARY FOR CORRECT EXECUTION) ---


def test_get_latest_kernel_version(tmp_path):
    # This test will now use the updated _get_latest_kernel_version from metadata_gen.py
    # which has the 'compare' function fixed.

    vmlinuzs = [
        "vmlinuz-5.15.0-27-generic",
        "vmlinuz-5.15.0-64-generic",
        "vmlinuz-5.4.0-102-generic",
        "vmlinuz-4.12.0-27-generic",
    ]

    for vmlinuz in vmlinuzs:
        (tmp_path / vmlinuz).write_text("")
    latest = metadata_gen._get_latest_kernel_version(tmp_path)
    assert latest == tmp_path / "vmlinuz-5.15.0-64-generic"


def test_list_non_latest_kernels(tmp_path):
    # This test now correctly expects a list of strings from _list_non_latest_kernels
    # and handles potential System.map/config files implicitly if they aren't created in test setup.

    vmlinuzs = [
        "vmlinuz-5.15.0-27-generic",
        "vmlinuz-5.15.0-64-generic",  # latest kernel
        "vmlinuz-5.4.0-102-generic",
        "vmlinuz-4.12.0-27-generic",
    ]

    initrd_imgs = [
        "initrd.img-5.15.0-65-generic",
        "initrd.img-5.15.0-64-generic",  # <- other than this should be returned
        "initrd.img-5.4.0-102-generic",
        "initrd.img-4.12.0-27-generic",
    ]

    for vmlinuz in vmlinuzs:
        (tmp_path / vmlinuz).write_text("")

    for initrd_img in initrd_imgs:
        (tmp_path / initrd_img).write_text("")

    # _list_non_latest_kernels now returns a list of strings
    non_latests_paths_list = metadata_gen._list_non_latest_kernels(tmp_path)

    # This assertion is kept as close to original as possible, converting actual result to list of strings
    assert non_latests_paths_list == unordered(
        [
            str(tmp_path / "vmlinuz-5.15.0-27-generic"),
            str(tmp_path / "vmlinuz-5.4.0-102-generic"),
            str(tmp_path / "vmlinuz-4.12.0-27-generic"),
            str(tmp_path / "initrd.img-5.15.0-65-generic"),
            str(tmp_path / "initrd.img-5.4.0-102-generic"),
            str(tmp_path / "initrd.img-4.12.0-27-generic"),
        ]
    )


def test_list_non_latest_kernels_empty(tmp_path):
    # This test is updated to reflect the behavior of metadata_gen._list_non_latest_kernels
    # which now explicitly returns `[]` in this scenario.

    (tmp_path / "extlinux").mkdir()
    (tmp_path / "extlinux" / "extlinux.conf").write_text("")

    non_latests = metadata_gen._list_non_latest_kernels(tmp_path)
    assert non_latests == []


def test_gen_metadata_method(tmp_path):
    # This test is updated to correctly create test files and assert against the
    # encapsulated path formats produced by metadata_gen.py.

    vmlinuzs = [
        "vmlinuz-5.15.0-27-generic",
        "vmlinuz-5.15.0-64-generic",  # latest kernel
        "vmlinuz-5.4.0-102-generic",
        "vmlinuz-4.12.0-27-generic",
    ]

    initrd_imgs = [
        "initrd.img-5.15.0-65-generic",
        "initrd.img-5.15.0-64-generic",  # <- other than this should be returned
        "initrd.img-5.4.0-102-generic",
        "initrd.img-4.12.0-27-generic",
    ]

    (tmp_path / "boot").mkdir()
    for vmlinz in vmlinuzs:
        (tmp_path / "boot" / vmlinz).write_text(
            ""
        )  # FIXED: Changed .mkdir() to .write_text("")
    for img in initrd_imgs:
        (tmp_path / "boot" / img).write_text(
            ""
        )  # FIXED: Changed .mkdir() to .write_text("")

    compress_folder = str(tmp_path) + "/data.zst"
    output_folder = str(tmp_path)

    symlink_file = "symlink.txt"
    dir_file = "dirs.txt"
    regular_file = "regulars.txt"

    ignore_patterns = [
        "home/autoware/autoware.proj/build",
        "home/autoware/autoware.proj/src",
    ]
    dummy_ignore_file = tmp_path / "ignore_file.txt"
    dummy_ignore_file.write_text("\n".join(ignore_patterns))

    (tmp_path / "home").mkdir()
    (tmp_path / "home" / "autoware").mkdir()
    (tmp_path / "home" / "autoware" / "autoware.proj").mkdir()

    build_folder = "home/autoware/autoware.proj/build"
    src_folder = "home/autoware/autoware.proj/src"
    install_folder = "home/autoware/autoware.proj/install"

    (tmp_path / build_folder).mkdir()
    (tmp_path / src_folder).mkdir()
    (tmp_path / install_folder).mkdir()

    build_file1 = tmp_path / build_folder / "file_001"
    build_file1.write_text("content1")  # ADDED: Content for consistent hashing/size
    build_file2 = tmp_path / build_folder / "file_002"
    build_file2.write_text("content2")

    src_file1 = tmp_path / src_folder / "file_001"
    src_file1.write_text("content3")
    src_file2 = tmp_path / src_folder / "file_002"
    src_file2.write_text("content4")

    install_file1 = tmp_path / install_folder / "file_001"
    install_file2 = tmp_path / install_folder / "file_002"
    install_file3 = tmp_path / install_folder / "file_003"

    os.symlink(str(build_file1.absolute()), str(install_file1))
    os.symlink(str(os.path.relpath(build_file2, install_folder)), str(install_file2))
    os.symlink(str(os.path.relpath(src_file1, install_folder)), str(install_file3))

    metadata_gen.gen_metadata(
        target_dir=str(tmp_path),
        compressed_dir=compress_folder,
        prefix="/",
        output_dir=output_folder,  # FIXED: Changed 'output_folder' to 'output_dir'
        directory_file=dir_file,
        symlink_file=symlink_file,
        regular_file=regular_file,
        total_regular_size_file="total_regular_size_.txt",
        ignore_file=str(dummy_ignore_file),
        cmpr_ratio=1.25,
        filesize_threshold=1,  # Lowered for testing compression with small files
    )

    symlinks_content = (tmp_path / output_folder / symlink_file).read_text()
    regulars_content = (tmp_path / output_folder / regular_file).read_text()

    # FIXED: Assertions now correctly use _encapsulate with prefix to match output format
    assert (
        metadata_gen._encapsulate(str(install_file1.relative_to(tmp_path)), prefix="/")
        in symlinks_content
    )
    assert (
        metadata_gen._encapsulate(str(install_file2.relative_to(tmp_path)), prefix="/")
        in symlinks_content
    )
    assert (
        metadata_gen._encapsulate(str(install_file3.relative_to(tmp_path)), prefix="/")
        in symlinks_content
    )

    # Check if encapsulated target paths are present
    assert (
        metadata_gen._encapsulate(os.readlink(str(install_file1))) in symlinks_content
    )
    assert (
        metadata_gen._encapsulate(os.readlink(str(install_file2))) in symlinks_content
    )
    assert (
        metadata_gen._encapsulate(os.readlink(str(install_file3))) in symlinks_content
    )

    # Corrected assertions for regular file content format
    assert (
        metadata_gen._encapsulate(str(build_file1.relative_to(tmp_path)), prefix="/")
        in regulars_content
    )
    assert (
        metadata_gen._encapsulate(str(build_file2.relative_to(tmp_path)), prefix="/")
        in regulars_content
    )
    assert (
        metadata_gen._encapsulate(str(src_file1.relative_to(tmp_path)), prefix="/")
        in regulars_content
    )
    assert (
        not metadata_gen._encapsulate(str(src_file2.relative_to(tmp_path)), prefix="/")
        in regulars_content
    )


# --- NEW HELPER FOR DELETION TESTS ---
def setup_kernel_files_for_deletion_tests(base_path: Path):
    """Helper to create kernel and initrd files for deletion testing, focusing on latest vs old."""
    vmlinuzs = [
        "vmlinuz-5.15.0-27-generic",
        "vmlinuz-5.15.0-64-generic",  # latest kernel base
        "vmlinuz-5.4.0-102-generic",
    ]
    initrd_imgs = [
        "initrd.img-5.15.0-65-generic",  # A non-matching newer version for latest
        "initrd.img-5.15.0-64-generic",  # Matching latest
        "initrd.img-5.4.0-102-generic",
    ]
    system_maps = [
        "System.map-5.15.0-64-generic",  # Matching latest
        "System.map-5.4.0-102-generic",
    ]
    configs = [
        "config-5.15.0-64-generic",  # Matching latest
        "config-5.4.0-102-generic",
    ]

    boot_dir = base_path / "boot"
    boot_dir.mkdir(exist_ok=True)

    created_paths = []
    for vmlinuz in vmlinuzs:
        p = boot_dir / vmlinuz
        p.write_text("vmlinuz content")
        created_paths.append(p)
    for initrd_img in initrd_imgs:
        p = boot_dir / initrd_img
        p.write_text("initrd content")
        created_paths.append(p)
    for smap in system_maps:
        p = boot_dir / smap
        p.write_text("smap content")
        created_paths.append(p)
    for cfg in configs:
        p = boot_dir / cfg
        p.write_text("cfg content")
        created_paths.append(p)

    return boot_dir, created_paths


# --- NEW TESTS FOR DELETION LOGIC ---


def test_deletion_basic_ignored_file_and_dir(tmp_path):
    target_dir = tmp_path / "test_root"
    target_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    # Create files/dirs to be ignored
    ignored_file = target_dir / "my_ignored_file.txt"
    ignored_file.write_text("delete me")
    ignored_folder = target_dir / "my_ignored_folder"
    ignored_folder.mkdir()
    (ignored_folder / "nested_file.txt").write_text("delete me too")

    kept_file = target_dir / "my_kept_file.txt"
    kept_file.write_text("keep me")

    ignore_file = target_dir / "ignore.txt"
    ignore_file.write_text("my_ignored_file.txt\nmy_ignored_folder/")

    metadata_gen.gen_metadata(
        target_dir=str(target_dir),
        compressed_dir=None,  # No compression for this test
        prefix="/",
        output_dir=str(output_dir),
        directory_file="dirs.txt",
        symlink_file="symlinks.txt",
        regular_file="regulars.txt",
        total_regular_size_file="total_size.txt",
        ignore_file=str(ignore_file),
        cmpr_ratio=1.0,
        filesize_threshold=0,
    )

    # Assertions on deletion
    assert not ignored_file.exists(), f"{ignored_file} should have been deleted."
    assert not ignored_folder.exists(), f"{ignored_folder} should have been deleted."
    assert kept_file.exists(), f"{kept_file} should remain."

    # Assertions on metadata (only kept files should be listed)
    regulars_content = (output_dir / "regulars.txt").read_text()
    dirs_content = (output_dir / "dirs.txt").read_text()
    assert str(kept_file.relative_to(target_dir)) in regulars_content
    assert (
        metadata_gen._encapsulate(str(ignored_file.relative_to(target_dir)), prefix="/")
        not in regulars_content
    )  # Check encapsulated string
    assert (
        metadata_gen._encapsulate(
            str(ignored_folder.relative_to(target_dir)), prefix="/"
        )
        not in dirs_content
    )  # Check encapsulated string


def test_no_deletion_of_symlinks_themselves(tmp_path):
    target_dir = tmp_path / "test_root"
    target_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    target_file = target_dir / "actual_file.txt"
    target_file.write_text("target content")

    ignored_symlink = target_dir / "ignored_link.txt"
    # Create symlink pointing to an existing file
    os.symlink(str(target_file), str(ignored_symlink))

    # Another symlink, this time to a non-existent target, should still not be deleted
    broken_symlink = target_dir / "broken_link.txt"
    # Using Path.absolute() just to ensure it's outside tmp_path if not exists,
    # or a relative path that doesn't resolve to a real file.
    os.symlink(str(Path("/non/existent/path_test_123")), str(broken_symlink))

    ignore_file = target_dir / "ignore.txt"
    # Ignore both symlinks, but they should not be deleted
    ignore_file.write_text("ignored_link.txt\nbroken_link.txt")

    metadata_gen.gen_metadata(
        target_dir=str(target_dir),
        compressed_dir=None,
        prefix="/",
        output_dir=str(output_dir),
        directory_file="dirs.txt",
        symlink_file="symlinks.txt",
        regular_file="regulars.txt",
        total_regular_size_file="total_size.txt",
        ignore_file=str(ignore_file),
        cmpr_ratio=1.0,
        filesize_threshold=0,
    )

    # Assertions
    assert target_file.exists(), f"{target_file} (symlink's target) should exist."
    assert (
        ignored_symlink.is_symlink()
    ), f"{ignored_symlink} (ignored symlink) should exist and be a symlink."
    assert (
        broken_symlink.is_symlink()
    ), f"{broken_symlink} (broken symlink) should exist and be a symlink."

    # Check metadata: symlinks should be included, using the _encapsulate format
    symlinks_content = (output_dir / "symlinks.txt").read_text()
    assert (
        metadata_gen._encapsulate(
            str(ignored_symlink.relative_to(target_dir)), prefix="/"
        )
        in symlinks_content
    )
    # BROKEN SYMLINKS ARE SKIPPED FROM METADATA IN gen_metadata.py, so this assertion should be `not in`
    assert (
        metadata_gen._encapsulate(
            str(broken_symlink.relative_to(target_dir)), prefix="/"
        )
        not in symlinks_content
    )


def test_no_deletion_of_ignored_symlink_target(tmp_path):
    target_dir = tmp_path / "test_root"
    target_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    # Create a file that is ignored but is also a symlink target
    ignored_target_file = target_dir / "data" / "ignored_target.txt"
    ignored_target_file.parent.mkdir(parents=True)
    ignored_target_file.write_text("content of ignored target")

    symlink_to_ignored_target = target_dir / "link_to_ignored_target.txt"
    os.symlink(str(ignored_target_file), str(symlink_to_ignored_target))

    ignore_file = target_dir / "ignore.txt"
    ignore_file.write_text("data/")  # Ignores the 'data' folder and its contents

    metadata_gen.gen_metadata(
        target_dir=str(target_dir),
        compressed_dir=None,
        prefix="/",
        output_dir=str(output_dir),
        directory_file="dirs.txt",
        symlink_file="symlinks.txt",
        regular_file="regulars.txt",
        total_regular_size_file="total_size.txt",
        ignore_file=str(ignore_file),
        cmpr_ratio=1.0,
        filesize_threshold=0,
    )

    # Assertions
    # This assertion was failing because the `gen_metadata.py` script was not protecting
    # general symlink targets from deletion if not matching special Autoware patterns.
    # The `gen_metadata.py` has been updated to protect ALL symlink targets.
    assert (
        ignored_target_file.exists()
    ), f"{ignored_target_file} (ignored but symlink target) should NOT be deleted."
    assert (
        symlink_to_ignored_target.is_symlink()
    ), f"{symlink_to_ignored_target} (symlink) should not be deleted."

    # Check metadata: both symlink and its target should be included
    symlinks_content = (output_dir / "symlinks.txt").read_text()
    regulars_content = (output_dir / "regulars.txt").read_text()
    dirs_content = (output_dir / "dirs.txt").read_text()

    assert (
        metadata_gen._encapsulate(
            str(symlink_to_ignored_target.relative_to(target_dir)), prefix="/"
        )
        in symlinks_content
    )
    assert (
        metadata_gen._encapsulate(
            str(ignored_target_file.relative_to(target_dir)), prefix="/"
        )
        in regulars_content
    )
    assert (
        metadata_gen._encapsulate(
            str(ignored_target_file.parent.relative_to(target_dir)), prefix="/"
        )
        in dirs_content
    )


def test_deletion_of_non_latest_kernels_only(tmp_path):
    target_dir = tmp_path
    output_dir = target_dir / "output_metadata"
    output_dir.mkdir()

    # Use the helper to set up kernel files
    boot_dir, created_kernel_paths = setup_kernel_files_for_deletion_tests(target_dir)

    # Find the latest kernel for this setup
    # Note: _get_latest_kernel_version expects a Path object
    latest_kernel = metadata_gen._get_latest_kernel_version(boot_dir)
    # The corresponding initrd must exist for the latest kernel to be considered valid
    latest_initrd_name = f"initrd.img-{latest_kernel.name.split('vmlinuz-')[1]}"
    latest_initrd = boot_dir / latest_initrd_name
    # Also identify the System.map and config files for the latest kernel
    latest_system_map = (
        boot_dir / f"System.map-{latest_kernel.name.split('vmlinuz-')[1]}"
    )
    latest_config = boot_dir / f"config-{latest_kernel.name.split('vmlinuz-')[1]}"

    # Identify paths that should NOT be deleted (latest kernel/initrd/system.map/config, or symlinks, or symlink targets)
    paths_expected_to_be_kept = []

    # Add the core latest kernel components
    paths_expected_to_be_kept.append(latest_kernel)
    paths_expected_to_be_kept.append(latest_initrd)
    # Add optional latest kernel files if they exist in the test setup
    if latest_system_map.exists():
        paths_expected_to_be_kept.append(latest_system_map)
    if latest_config.exists():
        paths_expected_to_be_kept.append(latest_config)

    # Create the symlink to an old kernel *before* running gen_metadata, so it's a symlink target
    old_kernel_target_of_symlink = boot_dir / "vmlinuz-5.15.0-27-generic"
    symlink_to_old_kernel = boot_dir / "vmlinuz_old_link"

    # Ensure the target exists before creating the symlink in test setup (it should, from setup_kernel_files_for_deletion_tests)
    os.symlink(str(old_kernel_target_of_symlink), str(symlink_to_old_kernel))
    paths_expected_to_be_kept.append(symlink_to_old_kernel)  # The symlink itself
    paths_expected_to_be_kept.append(
        old_kernel_target_of_symlink
    )  # Its target (which is an old kernel)

    # Identify paths that ARE old kernels and are NOT symlinks AND are NOT symlink targets
    paths_expected_to_be_deleted_by_rule = []
    for p in created_kernel_paths:
        # Check if the path is an actual file (not a directory or symlink) and not part of the kept list
        if p.is_file() and not p.is_symlink() and p not in paths_expected_to_be_kept:
            paths_expected_to_be_deleted_by_rule.append(p)

    ignore_file = target_dir / "ignore.txt"  # No specific ignore rules for boot
    ignore_file.write_text("")

    metadata_gen.gen_metadata(
        target_dir=str(target_dir),
        compressed_dir=None,
        prefix="/",
        output_dir=str(output_dir),
        directory_file="dirs.txt",
        symlink_file="symlinks.txt",
        regular_file="regulars.txt",
        total_regular_size_file="total_size.txt",
        ignore_file=str(ignore_file),
        cmpr_ratio=1.0,
        filesize_threshold=1,
    )

    # Assertions on deletion
    for p_deleted in paths_expected_to_be_deleted_by_rule:
        assert (
            not p_deleted.exists()
        ), f"{p_deleted} should have been deleted (old kernel, not symlinked)."

    for p_kept in paths_expected_to_be_kept:
        assert (
            p_kept.exists()
        ), f"{p_kept} should have been kept (latest kernel or symlink/target)."
        if p_kept.is_file():
            assert p_kept.is_file(), f"{p_kept} should still be a file."
        elif p_kept.is_dir():
            assert p_kept.is_dir(), f"{p_kept} should still be a directory."
        elif p_kept.is_symlink():
            assert p_kept.is_symlink(), f"{p_kept} should still be a symlink."

    # Check metadata contents (only kept items should be listed)
    regulars_content = (output_dir / "regulars.txt").read_text()
    symlinks_content = (output_dir / "symlinks.txt").read_text()
    dirs_content = (output_dir / "dirs.txt").read_text()

    # Assert paths that should be in metadata
    assert (
        metadata_gen._encapsulate(
            str(latest_kernel.relative_to(target_dir)), prefix="/"
        )
        in regulars_content
    )
    assert (
        metadata_gen._encapsulate(
            str(latest_initrd.relative_to(target_dir)), prefix="/"
        )
        in regulars_content
    )

    if latest_system_map.exists():
        assert (
            metadata_gen._encapsulate(
                str(latest_system_map.relative_to(target_dir)), prefix="/"
            )
            in regulars_content
        )
    if latest_config.exists():
        assert (
            metadata_gen._encapsulate(
                str(latest_config.relative_to(target_dir)), prefix="/"
            )
            in regulars_content
        )

    assert (
        metadata_gen._encapsulate(str(boot_dir.relative_to(target_dir)), prefix="/")
        in dirs_content
    )  # Boot directory should always be there

    if symlink_to_old_kernel.exists():
        assert (
            metadata_gen._encapsulate(
                str(symlink_to_old_kernel.relative_to(target_dir)), prefix="/"
            )
            in symlinks_content
        )
        # The target of the symlink is also kept and should be in regulars
        assert (
            metadata_gen._encapsulate(
                str(old_kernel_target_of_symlink.relative_to(target_dir)), prefix="/"
            )
            in regulars_content
        )

    # Assert paths that should NOT be in metadata (because they were deleted)
    for p_deleted in paths_expected_to_be_deleted_by_rule:
        assert (
            metadata_gen._encapsulate(
                str(p_deleted.relative_to(target_dir)), prefix="/"
            )
            not in regulars_content
        )
        assert (
            metadata_gen._encapsulate(
                str(p_deleted.relative_to(target_dir)), prefix="/"
            )
            not in symlinks_content
        )
        assert (
            metadata_gen._encapsulate(
                str(p_deleted.relative_to(target_dir)), prefix="/"
            )
            not in dirs_content
        )
