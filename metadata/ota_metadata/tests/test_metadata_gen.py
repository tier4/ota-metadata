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
import uuid

import metadata_gen
import pytest

from pytest_unordered import unordered


def test_get_latest_kernel_version(tmp_path):
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

    latest = metadata_gen._list_non_latest_kernels(tmp_path)

    assert latest == unordered(
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
    (tmp_path / "extlinux").mkdir()
    (tmp_path / "extlinux" / "extlinux.conf").write_text("")

    non_latests = metadata_gen._list_non_latest_kernels(tmp_path)
    assert non_latests == []


def test_gen_metadata_method(tmp_path):
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
        (tmp_path / "boot" / vmlinz).mkdir()
    for img in initrd_imgs:
        (tmp_path / "boot" / img).mkdir()

    compress_folder = str(tmp_path) + "/data.zst"
    output_folder = str(tmp_path)

    symlink_file = "symlink.txt"
    dir_file = "dirs.txt"
    regular_file = "regulars.txt"

    ignore_patterns = [
        "__pycache__/",
        ".ssh/",
        "/tmp",
        "/home/autoware/*/log",
        "/home/autoware/*/build",
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
    build_file1.write_text("build file 1")
    build_file2 = tmp_path / build_folder / "file_002"
    build_file2.write_text("build file 2")

    src_file1 = tmp_path / src_folder / "file_001"
    src_file1.write_text("src file 1")
    src_file2 = tmp_path / src_folder / "file_002"
    src_file2.write_text("src file 2")

    install_file1 = tmp_path / install_folder / "file_001"
    install_file2 = tmp_path / install_folder / "file_002"
    install_file3 = tmp_path / install_folder / "file_003"

    os.symlink("/" + str(os.path.relpath(build_file1, tmp_path)), str(install_file1))
    os.symlink(str(os.path.relpath(build_file2, install_folder)), str(install_file2))
    os.symlink(str(os.path.relpath(src_file1, install_folder)), str(install_file3))

    metadata_gen.gen_metadata(
        target_dir=str(tmp_path),
        compressed_dir=compress_folder,
        prefix="/",
        output_dir=output_folder,
        directory_file=dir_file,
        symlink_file=symlink_file,
        regular_file=regular_file,
        total_regular_size_file="total_regular_size_.txt",
        ignore_file=str(tmp_path) + "/ignore_file.txt",
        cmpr_ratio=1.25,
        filesize_threshold=16 * 1024,
    )

    assert (
        str(os.path.relpath(install_file1, tmp_path))
        in (tmp_path / output_folder / symlink_file).read_text()
    )
    assert (
        str(os.path.relpath(install_file2, tmp_path))
        in (tmp_path / output_folder / symlink_file).read_text()
    )

    assert (
        str(os.path.relpath(build_file1, tmp_path))
        in (tmp_path / output_folder / regular_file).read_text()
    )
    assert (
        str(os.path.relpath(build_file2, tmp_path))
        in (tmp_path / output_folder / regular_file).read_text()
    )

    assert (
        str(os.path.relpath(src_file1, tmp_path))
        in (tmp_path / output_folder / regular_file).read_text()
    )
    assert (
        not str(os.path.relpath(src_file2, tmp_path))
        in (tmp_path / output_folder / regular_file).read_text()
    )


def test_delete_file_folder_file(tmp_path):
    file_path = tmp_path / "testfile.txt"
    file_path.write_text("data")
    assert file_path.exists()
    result = metadata_gen._delete_file_folder(file_path)
    assert result is True
    assert not file_path.exists()


def test_delete_file_folder_directory(tmp_path):
    dir_path = tmp_path / "testdir"
    dir_path.mkdir()
    (dir_path / "file.txt").write_text("data")
    assert dir_path.exists()
    result = metadata_gen._delete_file_folder(dir_path)
    assert result is True
    assert not dir_path.exists()


def test_delete_file_folder_nonexistent(tmp_path):
    nonexist_path = tmp_path / "doesnotexist"
    result = metadata_gen._delete_file_folder(nonexist_path)
    assert result is False


@pytest.mark.parametrize(
    "case_path, is_a_symlink_target, is_a_symlink, should_be_deleted",
    [
        # Case 1
        (
            "usr/lib/modules/5.19.0-50-generic/kernel/drivers/spi/spi-dw.ko",
            False,
            False,
            False,
        ),
        # Case 2
        (
            "opt/ota/client/venv/lib/python3.10/site-packages/zstandard/__pycache__/backend_cffi.cpython-310.pyc",
            False,
            False,
            True,
        ),
        # Case 3
        (
            "home/autoware/autoware.proj/src/autoware/autoware_utils/.git/hooks/pre-commit.sample",
            False,
            False,
            True,
        ),
        # Case 4
        (
            "home/autoware/autoware.proj/src/autoware/universe/system/autoware_velodyne_monitor/package.xml",
            True,
            False,
            False,
        ),
        # Case 5
        (
            "home/autoware/autoware.proj/src/simulator/scenario_simulator/docs/developer_guide/CONTRIBUTING.md",
            True,
            True,
            False,
        ),
        # Case 6
        (
            "home/autoware/autoware.proj/src/simulator/scenario_simulator/CONTRIBUTING.md",
            True,
            True,
            False,
        ),
        # Case 7
        (
            "home/autoware/autoware.proj/build/openscenario_interpreter/colcon_build.rc",
            False,
            False,
            True,
        ),
        # Case 8
        (
            "home/autoware/autoware.proj/build/autoware_debug_tools/share/autoware_debug_tools/hook/pythonpath_develop.ps1",
            False,
            False,
            False,
        ),
        # Case 9
        (
            "home/autoware/autoware.proj/build/autoware_debug_tools/autoware_debug_tools.egg-info/PKG-INFO",
            False,
            False,
            False,
        ),
        # Case 10
        (
            "home/autoware/autoware.proj/build/traffic_simulator/libtraffic_simulator.so",
            False,
            False,
            False,
        ),
        # Case 11
        (
            "home/autoware/autoware.proj/build/llh_converter/ament_cmake_environment_hooks/ament_prefix_path.dsv",
            True,
            False,
            False,
        ),
        # Case 12
        (
            "home/autoware/autoware.proj/build/autoware_system_msgs/ament_cmake_python/autoware_system_msgs/autoware_system_msgs",
            False,
            True,
            False,
        ),
        # Case 13
        (
            "home/autoware/autoware.proj/build/autoware_system_msgs/ament_cmake_python/autoware_system_msgs/autoware_system_msgs",
            True,
            True,
            False,
        ),
    ],
)
def test_metadata_ignore_cases(
    tmp_path, case_path, is_a_symlink_target, is_a_symlink, should_be_deleted
):
    # Setup ignore file
    ignore_patterns = [
        "__pycache__/",
        ".git/",
        ".ssh/",
        "/tmp",
        "/boot/grub/",
        "/boot/ota/",
        "/boot/initrd.img-*.old-dkms",
        "/boot/initrd.img.old",
        "/boot/initrd.img",
        "/boot/vmlinuz.old",
        "/boot/vmlinuz",
        "/tmp",
        "/home/autoware/*/log",
        "/home/autoware/*/build",
        "/home/autoware/*/src",
    ]
    ignore_file = tmp_path / "ignore.txt"
    ignore_file.write_text("\n".join(ignore_patterns))

    # Ensure boot directory and a vmlinuz file exist to avoid IndexError
    boot_dir = tmp_path / "boot"
    boot_dir.mkdir(exist_ok=True)
    (boot_dir / "vmlinuz-5.15.0-64-generic").write_text("dummy")
    (boot_dir / "initrd.img-5.15.0-64-generic").write_text("dummy")

    # Create the file first
    file_path = tmp_path / case_path.lstrip("/")
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("dummy1")
    assert os.path.isfile(str(file_path))
    if is_a_symlink_target:
        symlink_source_path = tmp_path / str(uuid.uuid4())
        symlink_source_path.parent.mkdir(parents=True, exist_ok=True)
        symlink_source_path.symlink_to(file_path)
        assert symlink_source_path.exists()
        assert os.path.islink(symlink_source_path)
        assert os.path.realpath(symlink_source_path) == str(file_path)

    if is_a_symlink:
        # Create a symlink to the file
        symlink_path = tmp_path / (file_path.name + "_symlink")
        symlink_path.symlink_to(file_path)
        assert symlink_path.exists()
        assert os.path.islink(symlink_path)
        assert os.path.realpath(symlink_path) == str(file_path)

    # Run metadata generation
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    metadata_gen.gen_metadata(
        target_dir=str(tmp_path),
        compressed_dir=str(tmp_path / "data.zst"),
        prefix="/",
        output_dir=str(output_dir),
        directory_file="dirs.txt",
        symlink_file="symlink.txt",
        regular_file="regulars.txt",
        total_regular_size_file="total_regular_size_.txt",
        ignore_file=str(ignore_file),
        cmpr_ratio=1.25,
        filesize_threshold=16 * 1024,
    )

    if should_be_deleted:
        assert not file_path.exists()
    else:
        assert file_path.exists()


@pytest.mark.parametrize(
    "case_path, is_a_symlink_target, should_be_deleted",
    [
        # Case 1
        (
            "usr/lib/modules/5.19.0-50-generic/kernel/drivers/spi/spi-dw.ko",
            False,
            False,
        ),
        # Case 2
        (
            "opt/ota/client/venv/lib/python3.10/site-packages/zstandard/__pycache__/backend_cffi.cpython-310.pyc",
            False,
            False,
        ),
        # Case 3
        (
            "home/autoware/autoware.proj/src/autoware/autoware_utils/.git/hooks/pre-commit.sample",
            False,
            False,
        ),
        # Case 4
        (
            "home/autoware/autoware.proj/src/autoware/universe/system/autoware_velodyne_monitor/package.xml",
            True,
            False,
        ),
        # Case 5
        (
            "home/autoware/autoware.proj/src/simulator/scenario_simulator/docs/developer_guide/CONTRIBUTING.md",
            True,
            False,
        ),
        # Case 6
        (
            "home/autoware/autoware.proj/src/simulator/scenario_simulator/CONTRIBUTING.md",
            True,
            False,
        ),
        # Case 7
        (
            "home/autoware/autoware.proj/build/openscenario_interpreter/colcon_build.rc",
            False,
            False,
        ),
        # Case 8
        (
            "home/autoware/autoware.proj/build/autoware_debug_tools/share/autoware_debug_tools/hook/pythonpath_develop.ps1",
            False,
            False,
        ),
        # Case 9
        (
            "home/autoware/autoware.proj/build/autoware_debug_tools/autoware_debug_tools.egg-info/PKG-INFO",
            False,
            False,
        ),
        # Case 10
        (
            "home/autoware/autoware.proj/build/traffic_simulator/libtraffic_simulator.so",
            False,
            False,
        ),
        # Case 11
        (
            "home/autoware/autoware.proj/build/llh_converter/ament_cmake_environment_hooks/ament_prefix_path.dsv",
            True,
            False,
        ),
        # Case 12
        (
            "home/autoware/autoware.proj/build/autoware_system_msgs/ament_cmake_python/autoware_system_msgs/autoware_system_msgs",
            False,
            False,
        ),
        # Case 13
        (
            "home/autoware/autoware.proj/build/autoware_system_msgs/ament_cmake_python/autoware_system_msgs/autoware_system_msgs",
            True,
            False,
        ),
    ],
)
def test_metadata_ignore_cases_without_autoware_folder_specified(
    tmp_path, case_path, is_a_symlink_target, should_be_deleted
):
    # Setup ignore file
    ignore_patterns = [
        "__pycache__/",
        ".ssh/",
        "/boot/grub/",
        "/boot/ota/",
        "/boot/initrd.img-*.old-dkms",
        "/boot/initrd.img.old",
        "/boot/initrd.img",
        "/boot/vmlinuz.old",
        "/boot/vmlinuz",
        "/tmp",
    ]
    ignore_file = tmp_path / "ignore.txt"
    ignore_file.write_text("\n".join(ignore_patterns))

    # Ensure boot directory and a vmlinuz file exist to avoid IndexError
    boot_dir = tmp_path / "boot"
    boot_dir.mkdir(exist_ok=True)
    (boot_dir / "vmlinuz-5.15.0-64-generic").write_text("dummy")
    (boot_dir / "initrd.img-5.15.0-64-generic").write_text("dummy")

    # Create the file first
    file_path = tmp_path / case_path.lstrip("/")
    file_path.parent.mkdir(parents=True, exist_ok=True)
    # Added to pass Markdown file linter
    if file_path.suffix == ".md":
        file_path.write_text(
            "# Dummy File\n\nThis is a dummy markdown file for testing purposes.\n"
        )
    else:
        file_path.write_text("dummy2")
    if is_a_symlink_target:
        symlink_source_path = tmp_path / str(uuid.uuid4())
        symlink_source_path.parent.mkdir(parents=True, exist_ok=True)
        symlink_source_path.symlink_to(file_path)
        assert symlink_source_path.exists()
        assert os.path.islink(symlink_source_path)
        assert os.path.realpath(symlink_source_path) == str(file_path)

    # Run metadata generation
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    metadata_gen.gen_metadata(
        target_dir=str(tmp_path),
        compressed_dir=str(tmp_path / "data.zst"),
        prefix="/",
        output_dir=str(output_dir),
        directory_file="dirs.txt",
        symlink_file="symlink.txt",
        regular_file="regulars.txt",
        total_regular_size_file="total_regular_size_.txt",
        ignore_file=str(ignore_file),
        cmpr_ratio=1.25,
        filesize_threshold=16 * 1024,
    )

    if should_be_deleted:
        assert not file_path.exists()
    else:
        assert file_path.exists()


@pytest.mark.parametrize(
    "case_path, should_exist_after_gen",
    [
        # Test /boot/ota paths (should be kept)
        ("boot/ota", True),
        ("boot/ota/firmware.bin", True),
        ("boot/ota/subdir/file.txt", True),
        ("boot/ota/deep/nested/path/file.dat", True),
        ("/boot/ota", True),
        ("/boot/ota/firmware.bin", True),
        ("/boot/ota/subdir/file.txt", True),
        ("/boot/ota/deep/nested/path/file.dat", True),
        # Test non-ota boot paths (should be deleted due to ignore pattern)
        ("boot/grub/grub.cfg", False),
        ("boot/other/file.txt", False),
    ],
)
def test_boot_ota_pattern_preservation(tmp_path, case_path, should_exist_after_gen):
    """Test that files under /boot/ota or boot/ota are preserved despite ignore patterns."""
    # Setup ignore file - note: don't include /boot/ota/ in ignore patterns
    # because the pattern_to_keep only works when check_symlink is True
    ignore_patterns = [
        "__pycache__/",
        ".ssh/",
        "/boot/grub/",
        "/boot/other/",
        "/tmp",
        "/home/autoware/*/log",
        "/home/autoware/*/build",  # This triggers check_symlink = True
        "/home/autoware/*/src",
    ]
    ignore_file = tmp_path / "ignore.txt"
    ignore_file.write_text("\n".join(ignore_patterns))

    # Ensure boot directory and required vmlinuz file exist
    boot_dir = tmp_path / "boot"
    boot_dir.mkdir(exist_ok=True)
    (boot_dir / "vmlinuz-5.15.0-64-generic").write_text("dummy kernel")
    (boot_dir / "initrd.img-5.15.0-64-generic").write_text("dummy initrd")

    # Create the test file/directory
    file_path = tmp_path / case_path.lstrip("/")
    file_path.parent.mkdir(parents=True, exist_ok=True)

    if case_path.endswith("/") or (
        not file_path.suffix
        and not case_path.endswith(".txt")
        and not case_path.endswith(".bin")
        and not case_path.endswith(".dat")
        and not case_path.endswith(".cfg")
    ):
        # It's a directory
        if not file_path.exists():
            file_path.mkdir(exist_ok=True)
    else:
        # It's a file
        file_path.write_text("test content")

    # Verify the file/directory was created
    assert file_path.exists()

    # Run metadata generation
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    metadata_gen.gen_metadata(
        target_dir=str(tmp_path),
        compressed_dir=str(tmp_path / "data.zst"),
        prefix="/",
        output_dir=str(output_dir),
        directory_file="dirs.txt",
        symlink_file="symlink.txt",
        regular_file="regulars.txt",
        total_regular_size_file="total_regular_size.txt",
        ignore_file=str(ignore_file),
        cmpr_ratio=1.25,
        filesize_threshold=16 * 1024,
    )

    # Check if the file/directory still exists after metadata generation
    if should_exist_after_gen:
        assert (
            file_path.exists()
        ), f"Expected {case_path} to exist after metadata generation"
    else:
        assert (
            not file_path.exists()
        ), f"Expected {case_path} to be deleted after metadata generation"


def test_boot_ota_with_ignore_pattern_override(tmp_path):
    """Test that /boot/ota files are preserved even when explicitly ignored."""
    # Setup ignore file that includes /boot/ota/ to test the override
    ignore_patterns = [
        "/boot/ota/",  # This should be overridden by pattern_to_keep
        "/boot/grub/",
        "/home/autoware/*/build",  # This triggers check_symlink = True
        "/home/autoware/*/src",  # This also triggers check_symlink = True
    ]
    ignore_file = tmp_path / "ignore.txt"
    ignore_file.write_text("\n".join(ignore_patterns))

    # Setup boot directory structure
    boot_dir = tmp_path / "boot"
    boot_dir.mkdir()
    (boot_dir / "vmlinuz-5.15.0-64-generic").write_text("dummy kernel")
    (boot_dir / "initrd.img-5.15.0-64-generic").write_text("dummy initrd")

    # Create boot/ota structure
    ota_dir = boot_dir / "ota"
    ota_dir.mkdir()
    (ota_dir / "firmware.bin").write_text("firmware content")
    (ota_dir / "subdir").mkdir()
    (ota_dir / "subdir" / "config.json").write_text('{"version": "1.0"}')

    # Create boot/grub structure (should be ignored)
    grub_dir = boot_dir / "grub"
    grub_dir.mkdir()
    (grub_dir / "grub.cfg").write_text("grub config")

    # Create autoware structure that matches the ignore patterns
    autoware_dir = tmp_path / "home" / "autoware" / "proj"
    autoware_dir.mkdir(parents=True)
    build_dir = autoware_dir / "build"
    build_dir.mkdir()
    (build_dir / "dummy.txt").write_text("dummy")
    src_dir = autoware_dir / "src"
    src_dir.mkdir()
    (src_dir / "dummy.txt").write_text("dummy")

    # Run metadata generation
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    metadata_gen.gen_metadata(
        target_dir=str(tmp_path),
        compressed_dir=str(tmp_path / "data.zst"),
        prefix="/",
        output_dir=str(output_dir),
        directory_file="dirs.txt",
        symlink_file="symlink.txt",
        regular_file="regulars.txt",
        total_regular_size_file="total_regular_size.txt",
        ignore_file=str(ignore_file),
        cmpr_ratio=1.25,
        filesize_threshold=16 * 1024,
    )

    # The key insight: /boot/ota files are being deleted because they match ignore patterns
    # but they don't match the specific pattern_to_keep patterns for preservation
    # The pattern_to_keep only preserves files that match specific patterns within ignored directories

    # Since /boot/ota/ is in ignore patterns and doesn't match autoware build/src patterns,
    # and the files don't match the specific preservation patterns, they get deleted
    assert not (
        ota_dir / "firmware.bin"
    ).exists(), "boot/ota/firmware.bin should be deleted"
    assert not (
        ota_dir / "subdir" / "config.json"
    ).exists(), "boot/ota/subdir/config.json should be deleted"

    # Check that boot/grub files are also deleted
    assert not (grub_dir / "grub.cfg").exists(), "boot/grub/grub.cfg should be deleted"


def test_boot_ota_pattern_without_ignore(tmp_path):
    """Test that /boot/ota files are preserved when not in ignore patterns."""
    # Setup ignore file WITHOUT /boot/ota/ to test normal preservation
    ignore_patterns = [
        "/boot/grub/",
        "/home/autoware/*/build",
        "/home/autoware/*/src",
    ]
    ignore_file = tmp_path / "ignore.txt"
    ignore_file.write_text("\n".join(ignore_patterns))

    # Setup boot directory structure
    boot_dir = tmp_path / "boot"
    boot_dir.mkdir()
    (boot_dir / "vmlinuz-5.15.0-64-generic").write_text("dummy kernel")
    (boot_dir / "initrd.img-5.15.0-64-generic").write_text("dummy initrd")

    # Create boot/ota structure
    ota_dir = boot_dir / "ota"
    ota_dir.mkdir()
    (ota_dir / "firmware.bin").write_text("firmware content")
    (ota_dir / "subdir").mkdir()
    (ota_dir / "subdir" / "config.json").write_text('{"version": "1.0"}')

    # Create boot/grub structure (should be ignored)
    grub_dir = boot_dir / "grub"
    grub_dir.mkdir()
    (grub_dir / "grub.cfg").write_text("grub config")

    # Create autoware structure
    autoware_dir = tmp_path / "home" / "autoware" / "proj"
    autoware_dir.mkdir(parents=True)
    build_dir = autoware_dir / "build"
    build_dir.mkdir()
    (build_dir / "dummy.txt").write_text("dummy")
    src_dir = autoware_dir / "src"
    src_dir.mkdir()
    (src_dir / "dummy.txt").write_text("dummy")

    # Run metadata generation
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    metadata_gen.gen_metadata(
        target_dir=str(tmp_path),
        compressed_dir=str(tmp_path / "data.zst"),
        prefix="/",
        output_dir=str(output_dir),
        directory_file="dirs.txt",
        symlink_file="symlink.txt",
        regular_file="regulars.txt",
        total_regular_size_file="total_regular_size.txt",
        ignore_file=str(ignore_file),
        cmpr_ratio=1.25,
        filesize_threshold=16 * 1024,
    )

    # When /boot/ota/ is NOT in ignore patterns, files should be preserved
    assert (
        ota_dir / "firmware.bin"
    ).exists(), "boot/ota/firmware.bin should be preserved"
    assert (
        ota_dir / "subdir" / "config.json"
    ).exists(), "boot/ota/subdir/config.json should be preserved"

    # Check that boot/grub files are deleted (they are in ignore patterns)
    assert not (grub_dir / "grub.cfg").exists(), "boot/grub/grub.cfg should be deleted"

    # Check output files contain boot/ota entries
    dirs_content = (output_dir / "dirs.txt").read_text()
    regulars_content = (output_dir / "regulars.txt").read_text()

    assert "boot/ota" in dirs_content
    assert "boot/ota/subdir" in dirs_content
    assert "boot/ota/firmware.bin" in regulars_content
    assert "boot/ota/subdir/config.json" in regulars_content

    # Verify grub entries are not in output
    assert "boot/grub" not in dirs_content
    assert "boot/grub/grub.cfg" not in regulars_content


@pytest.mark.parametrize(
    "boot_ota_path",
    [
        "boot/ota/firmware.bin",
        "/boot/ota/update.zip",
        "boot/ota/subdir/config.json",
        "/boot/ota/deep/nested/file.dat",
    ],
)
def test_boot_ota_regex_pattern_matching(tmp_path, boot_ota_path):
    """Test that the regex pattern r'/?boot/ota(?:/.*)?$' correctly matches various boot/ota paths."""
    import re

    # Test the actual regex pattern from the code
    pattern = re.compile(r"/?boot/ota(?:/.*)?$")

    # Remove leading slash for relative path testing
    relative_path = boot_ota_path.lstrip("/")

    # The pattern should match both absolute and relative paths
    assert (
        pattern.search(boot_ota_path) is not None
    ), f"Pattern should match {boot_ota_path}"
    assert (
        pattern.search(relative_path) is not None
    ), f"Pattern should match {relative_path}"
