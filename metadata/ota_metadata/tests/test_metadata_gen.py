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

import metadata_gen
import os

from pytest_unordered import unordered
from pathlib import Path


def test_get_latest_kernel_version(tmp_path):
    import metadata_gen

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
    import metadata_gen

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
    import metadata_gen

    (tmp_path / "extlinux").mkdir()
    (tmp_path / "extlinux" / "extlinux.conf").write_text("")

    non_latests = metadata_gen._list_non_latest_kernels(tmp_path)
    assert non_latests == []


def test_gen_metadata_method(tmp_path):
    import metadata_gen
    import os

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
    build_file1.write_text("")
    build_file2 = tmp_path / build_folder / "file_002"
    build_file2.write_text("")

    src_file1 = tmp_path / src_folder / "file_001"
    src_file1.write_text("")
    src_file2 = tmp_path / src_folder / "file_002"
    src_file2.write_text("")

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
    # Check deleted_old_kernels.txt
    deleted_kernels_file = tmp_path / "deleted_old_kernels.txt"
    with open(deleted_kernels_file) as f:
        deleted_kernels = set(line.strip() for line in f if line.strip())

    expected_kernel_deleted = {
        str((tmp_path / "boot" / "vmlinuz-5.15.0-27-generic").resolve()),
        str((tmp_path / "boot" / "vmlinuz-5.4.0-102-generic").resolve()),
        str((tmp_path / "boot" / "vmlinuz-4.12.0-27-generic").resolve()),
        str((tmp_path / "boot" / "initrd.img-5.15.0-65-generic").resolve()),
        str((tmp_path / "boot" / "initrd.img-5.4.0-102-generic").resolve()),
        str((tmp_path / "boot" / "initrd.img-4.12.0-27-generic").resolve()),
    }
    assert expected_kernel_deleted.issubset(deleted_kernels)

    # Check deleted_ignore_files.txt
    deleted_ignore_file = tmp_path / "deleted_ignore_files.txt"
    with open(deleted_ignore_file) as f:
        deleted_ignored = set(line.strip() for line in f if line.strip())

    expected_ignored = {
        str(
            (
                tmp_path / "home" / "autoware" / "autoware.proj" / "build" / "file_001"
            ).resolve()
        ),
        str(
            (
                tmp_path / "home" / "autoware" / "autoware.proj" / "build" / "file_002"
            ).resolve()
        ),
        str(
            (
                tmp_path / "home" / "autoware" / "autoware.proj" / "src" / "file_001"
            ).resolve()
        ),
        str(
            (
                tmp_path / "home" / "autoware" / "autoware.proj" / "src" / "file_002"
            ).resolve()
        ),
    }
    assert expected_ignored.issubset(deleted_ignored)


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


def test_write_delete_list(tmp_path):
    deleted_set = {str(tmp_path / "a.txt"), str(tmp_path / "b.txt")}
    output_file = tmp_path / "deleted.txt"
    metadata_gen._write_delete_list(deleted_set, output_file)
    lines = output_file.read_text().splitlines()
    assert set(lines) == deleted_set


def test_delete_and_write_integration(tmp_path):
    file1 = tmp_path / "f1.txt"
    file2 = tmp_path / "f2.txt"
    file1.write_text("1")
    file2.write_text("2")
    deleted = set()
    for f in [file1, file2]:
        if metadata_gen._delete_file_folder(f):
            deleted.add(str(f))
    output_file = tmp_path / "deleted.txt"
    metadata_gen._write_delete_list(deleted, output_file)
    assert set(output_file.read_text().splitlines()) == deleted
