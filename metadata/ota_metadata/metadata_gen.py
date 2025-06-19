#!/usr/bin/env python3

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


import argparse
import glob
import os
import re
import shutil
import zstandard

from functools import cmp_to_key
from hashlib import sha256
from igittigitt import IgnoreParser
from packaging import version
from pathlib import Path
from typing import Set, List


ZSTD_COMPRESSION_EXTENSION = "zst"
ZSTD_COMPRESSION_LEVEL = 10
ZSTD_MULTITHREADS = 2
CHUNK_SIZE = 4 * (1024**2)  # 4MiB


def zstd_compress_file(
    cctx: zstandard.ZstdCompressor,
    src_fpath: str,
    dst_fpath: str,
    *,
    cmpr_ratio: float,
    filesize_threshold: int,
) -> bool:
    if (src_size := os.path.getsize(src_fpath)) < filesize_threshold:
        return False  # skip file with too small size
    # NOTE: interrupt the whole process if compression failed
    with open(src_fpath, "rb") as src_f, open(dst_fpath, "wb") as dst_f:
        with cctx.stream_writer(dst_f, size=src_size) as compressor:
            while data := src_f.read(CHUNK_SIZE):
                compressor.write(data)
    # drop compressed file if cmpr ratio is too small or compressed failed
    if (
        not (compressed_bytes := os.path.getsize(dst_fpath))
        or src_size / compressed_bytes < cmpr_ratio
    ):
        try:
            os.remove(dst_fpath)
        except OSError:
            pass
        return False
    # everything is fine, return True here
    return True


def _file_sha256(filename):
    one_mb = 1048576
    with open(filename, "rb") as f:
        m = sha256()
        while True:
            d = f.read(one_mb)
            if d == b"":
                break
            m.update(d)
        return m.hexdigest()


def _is_regular(path):
    return os.path.isfile(path) and not os.path.islink(path)


def _encapsulate(name, prefix=""):
    escaped = name.replace("'", "'\\''")
    return f"'{os.path.join(prefix, escaped)}'"


def _decapsulate(name):
    return name[1:-1].replace("'\\''", "'")


def _path_stat(base, path):
    return os.lstat(os.path.join(base, path))  # NOTE: lstat doesn't follow symlink


# return array of mode, uid and gid
def _path_mode_uid_gid(base, path, nlink=False):
    stat = _path_stat(base, path)
    if not nlink:
        return [oct(stat.st_mode)[-4:], str(stat.st_uid), str(stat.st_gid)]
    else:
        return [
            oct(stat.st_mode)[-4:],
            str(stat.st_uid),
            str(stat.st_gid),
            str(stat.st_nlink),
        ]


def _join_mode_uid_gid(base, path, nlink=False):
    return ",".join(_path_mode_uid_gid(base, path, nlink=nlink))


def ignore_rules(target_dir, ignore_file):
    ignore_parser = IgnoreParser()
    try:
        with open(ignore_file) as f:
            for line in f:
                line = line.rstrip("\n")
                ignore_parser.add_rule(line, base_path=target_dir)
    except Exception as e:
        print(
            f"Error reading ignore file '{ignore_file}': {e}. No files will be ignored based on rules."
        )
        raise
    return ignore_parser


def _delete_file(path: str) -> bool:
    """
    Delete a file at the given path.
    Returns True if the file was deleted, False if exception occurred.
    """
    try:
        file_path = Path(path)
        file_path.unlink(missing_ok=True)
        return True
    except Exception as e:
        print(f"Error deleting file {path}: {e}")
        raise


def _delete_folder(path: str) -> bool:
    """
    Delete a folder at the given path.
    Returns True if the folder was deleted, False if exception occurred.
    """
    try:
        folder_path = Path(path)
        if folder_path.exists() and folder_path.is_dir():
            shutil.rmtree(folder_path)
            return True
        return False
    except Exception as e:
        print(f"Error deleting folder {path}: {e}")
        raise


def _get_latest_kernel_version(boot_dir: Path) -> Path:
    kfiles_path = str(boot_dir / "vmlinuz-*.*.*-*-*")

    kfile_glob = [f for f in glob.glob(kfiles_path) if not Path(f).is_symlink()]
    kfiles = sorted(kfile_glob, key=cmp_to_key(compare), reverse=True)

    return Path(kfiles[0])  # latest


def compare(left: str, right: str) -> int:
    pa = re.compile(r"vmlinuz-(?P<version>\d+\.\d+\.\d+-\d+)(?P<suffix>.*)")
    ma_l = pa.match(Path(left).name)
    ma_r = pa.match(Path(right).name)
    ver_l = version.parse(ma_l["version"])
    ver_r = version.parse(ma_r["version"])
    return 1 if ver_l > ver_r else -1


def _list_non_latest_kernels(boot_dir: Path) -> list[str]:
    # if boot/extlinux/extlinux.conf exists, the kernel is specified in that file
    # so we don't need to pickup the latest kernel.
    if (boot_dir / "extlinux" / "extlinux.conf").is_file():
        return []

    kfiles_path = str(boot_dir / "vmlinuz-*.*.*-*-*")
    ifiles_path = str(boot_dir / "initrd.img-*.*.*-*-*")
    sfiles_path = str(boot_dir / "System.map-*.*.*-*-*")
    cfiles_path = str(boot_dir / "config-*.*.*-*-*")

    kfile_glob = [f for f in glob.glob(kfiles_path) if not Path(f).is_symlink()]
    ifile_glob = [f for f in glob.glob(ifiles_path) if not Path(f).is_symlink()]
    sfile_glob = [f for f in glob.glob(sfiles_path) if not Path(f).is_symlink()]
    cfile_glob = [f for f in glob.glob(cfiles_path) if not Path(f).is_symlink()]

    pa = re.compile(r"vmlinuz-(?P<version>\d+\.\d+\.\d+-\d+)(?P<suffix>.*)")
    vmlinuz = _get_latest_kernel_version(boot_dir)

    k_ma = pa.match(vmlinuz.name)
    ver = k_ma["version"]  # type: ignore
    suf = k_ma["suffix"]  # type: ignore
    initrd_img = vmlinuz.parent / f"initrd.img-{ver}{suf}"
    system_map = vmlinuz.parent / f"System.map-{ver}{suf}"
    config = vmlinuz.parent / f"config-{ver}{suf}"

    if str(initrd_img) not in ifile_glob:  # initrd.img-{ver}{suf} must exist.
        raise Exception(f"{initrd_img} doesn't exist.")

    kfile_glob.remove(str(vmlinuz))
    ifile_glob.remove(str(initrd_img))
    try:
        sfile_glob.remove(str(system_map))  # system_map is optional
        cfile_glob.remove(str(config))  # config is optional
    except ValueError:
        pass
    return kfile_glob + ifile_glob + sfile_glob + cfile_glob


def gen_metadata(
    target_dir,
    compressed_dir,
    prefix,
    output_dir,
    directory_file,
    symlink_file,
    regular_file,
    total_regular_size_file,
    ignore_file,
    *,
    cmpr_ratio: float,
    filesize_threshold: int,
):
    p = Path(target_dir)
    target_abs = Path(os.path.abspath(target_dir))
    ignore = ignore_rules(target_dir, ignore_file)

    # If ignore file has the following directories:
    #    1, "home/autoware/*/build"
    #    2, "home/autoware/*/src"
    # We will NOT simply ignore files under them.
    # We will check the following:
    #    1, If the file is set as the target of a symblink ?
    #    2, If the file falls in some special folder pattern ?
    # Why we need to do this? It is explained in this document
    # https://tier4.atlassian.net/wiki/x/JoC21Q
    check_patterns = [
        re.compile(r"home/autoware/[^/]+/build"),
        re.compile(r"home/autoware/[^/]+/src"),
    ]

    # This is the flag to control if we will check and add files back to "build" and "src" folder
    check_symlink = any(
        _pattern.search(str(_rule))
        for _rule in ignore.rules
        for _pattern in check_patterns
    )

    # Special Patterns that we need to check and add files.
    build_folder_patterns = [
        re.compile(r"home/autoware/[^/]*/build/.*/hook/.*"),
        re.compile(r"home/autoware/[^/]*/build/.*/.*.egg-info/.*"),
        re.compile(r"home/autoware/[^/]*/build/.*/.*.so$"),
    ]

    # Store paths for deletion, and for metadata generation
    paths_to_delete_abs: Set[Path] = set()
    metadata_symlinks: List[Path] = []  # Symlinks to collect for metadata
    metadata_dirs: List[Path] = []  # Directories to collect for metadata
    metadata_regulars: List[Path] = []  # Regular files to collect for metadata

    additional_regular_set = set()
    additional_dir_set = set()

    # remove kernels under /boot directory other than latest
    # _list_non_latest_kernels returns a list of strings, convert to Path objects for comparisons
    non_latest_kernels_str = _list_non_latest_kernels(p / "boot")
    non_latest_kernels_abs: Set[Path] = {
        Path(f_str) for f_str in non_latest_kernels_str
    }  # Convert to Set of Paths

    for f_abs in p.glob("**/*"):  # Iterate using Path objects
        try:
            # Skip broken symlinks from processing early
            if f_abs.is_symlink() and not f_abs.exists():
                print(
                    f"WARN: Broken symlink detected: {f_abs}. Skipping metadata collection."
                )
                continue  # Skip this broken symlink from metadata and deletion consideration

            f_rel = f_abs.relative_to(target_dir)  # Path object for relative path

            is_ignored = ignore.match(
                target_abs / str(f_rel)
            )  # Match using absolute path of relative
            is_symlink = f_abs.is_symlink()
            is_non_latest_kernel = (
                f_abs in non_latest_kernels_abs
            )  # Check against Path objects

            # If it's a symlink, always collect it for metadata and ensure it's not marked for deletion
            if is_symlink:
                metadata_symlinks.append(f_rel)
                continue  # Symlinks are never deleted, move to next file

            # --- Determine if the file/directory should be deleted or included in metadata ---
            should_be_deleted = False

            # Rule 1: Non-latest kernels are marked for deletion
            if is_non_latest_kernel:
                should_be_deleted = True
            # Rule 2: Ignored files/directories are marked for deletion, unless specially protected
            elif is_ignored:
                should_be_kept_despite_ignore_rule = False
                if (
                    check_symlink
                ):  # check_symlink is true if "home/autoware/*/build" or "home/autoware/*/src" rules are present
                    relative_path_str = str(f_rel)  # Use string for regex matching
                    is_in_special_autoware_pattern = any(
                        pattern.search(relative_path_str) for pattern in check_patterns
                    )

                    if is_in_special_autoware_pattern:
                        if f_abs.is_dir():
                            should_be_kept_despite_ignore_rule = True
                        elif f_abs.is_file() and any(
                            _file_pattern.search(relative_path_str)
                            for _file_pattern in build_folder_patterns
                        ):
                            should_be_kept_despite_ignore_rule = True

                if not should_be_kept_despite_ignore_rule:
                    should_be_deleted = True

            if should_be_deleted:
                paths_to_delete_abs.add(f_abs)  # Mark for deletion
            else:
                # Add to metadata lists if not marked for deletion
                if f_abs.is_dir():
                    metadata_dirs.append(f_rel)
                elif f_abs.is_file():
                    metadata_regulars.append(f_rel)

        except Exception as e:
            if str(e).startswith("Symlink loop from"):
                print(f"WARN: {e}")
            else:
                print(f"Error processing path {f_abs}: {e}. Skipping.")
            continue  # Continue loop even on error

        # SECOND PASS - Protect symlink targets from deletion and ensure they are in metadata
        # This ensures files/directories that are targets of symlinks (and exist) are never deleted.
    protected_by_symlink_targets: Set[Path] = (
        set()
    )  # To store relative paths to add to metadata

    for (
        symlink_rel_path
    ) in (
        metadata_symlinks
    ):  # Use metadata_symlinks for symlinks that will be in manifest
        try:
            symlink_abs_path = p / symlink_rel_path
            symlink_target_raw = os.readlink(str(symlink_abs_path))

            # Resolve the absolute path of the symlink target
            if Path(symlink_target_raw).is_absolute():
                target_abs_path = Path(target_abs.root) / symlink_target_raw.lstrip(
                    os.sep
                )
            else:
                target_abs_path = (
                    symlink_abs_path.parent / symlink_target_raw
                ).resolve()

            # If the target exists and is within the target_dir, protect it and its parent directories
            if target_abs_path.exists() and target_abs_path.is_relative_to(target_abs):
                target_rel_path = target_abs_path.relative_to(target_dir)

                # Add the target and its parents to the set of paths to be protected and included in metadata
                parts = target_rel_path.parts
                current_partial_path = Path()
                for part in parts:
                    if part:
                        current_partial_path /= part
                        abs_current_partial_path = p / current_partial_path
                        if abs_current_partial_path.is_symlink():
                            # If a symlink is encountered on the path to target, stop.
                            # The symlink itself is already handled in metadata_symlinks.
                            break

                        protected_by_symlink_targets.add(current_partial_path)
                        # Remove from deletion candidates if this path was previously marked
                        if abs_current_partial_path in paths_to_delete_abs:
                            paths_to_delete_abs.discard(abs_current_partial_path)
            else:
                print(
                    f"INFO: Symlink {symlink_rel_path} targets outside {target_dir} or to non-existent target: {symlink_target_raw}. Not protecting target from deletion."
                )

        except OSError as e:
            print(
                f"WARN: Failed to read symlink target for {symlink_rel_path}: {e}. Skipping target protection."
            )
        except Exception as e:
            print(
                f"Error processing symlink target for {symlink_rel_path}: {e}. Skipping protection."
            )

    # Consolidate 'additional' sets and 'protected by symlink' targets into main metadata lists
    # Use sets for merging to handle duplicates, then convert back to sorted lists
    final_dirs_set = set(metadata_dirs)
    final_regulars_set = set(metadata_regulars)

    # Add items from additional_sets (from check_symlink logic)
    final_dirs_set.update(Path(d_str) for d_str in additional_dir_set)
    final_regulars_set.update(Path(r_str) for r_str in additional_regular_set)

    # Add items protected by symlink targets
    for p_rel in protected_by_symlink_targets:
        f_abs_check = p / p_rel  # Absolute path to check if it's a file or dir
        if f_abs_check.is_dir():
            final_dirs_set.add(p_rel)
        elif f_abs_check.is_file():
            final_regulars_set.add(p_rel)

    # Convert sets back to sorted lists for final metadata output
    dirs_for_metadata = sorted(list(final_dirs_set))
    regulars_for_metadata = sorted(list(final_regulars_set))
    symlinks_for_metadata = sorted(
        list(metadata_symlinks)
    )  # Already collected as Path objects

    # --- Perform Deletion ---
    # Filter paths_to_delete_abs to ensure only existing files/folders are considered for deletion
    # (some might have been removed if part of a parent that got deleted).
    files_to_delete = sorted(
        [x for x in paths_to_delete_abs if x.is_file()],
        key=lambda x: str(x),
        reverse=True,  # Delete files deeper in hierarchy first
    )
    folders_to_delete = sorted(
        [x for x in paths_to_delete_abs if x.is_dir()],
        key=lambda x: str(x),
        reverse=True,  # Delete subfolders before parent folders
    )

    print("\n--- Files and Folders to be Deleted ---")
    if files_to_delete:
        print("Files to delete:")
        for f in files_to_delete:
            print(f"  - {f}")
    else:
        print("No files to delete.")

    if folders_to_delete:
        print("Folders to delete:")
        for f in folders_to_delete:
            print(f"  - {f}")
    else:
        print("No folders to delete.")

    print("\n--- Initiating Deletion Process ---")
    for file_path in files_to_delete:
        success = _delete_file(str(file_path))
        if success:
            print(f"  SUCCESS: {file_path}")
        else:
            print(f"  FAILED: {file_path}")  # _delete_file already prints error details

    for folder_path in folders_to_delete:
        success = _delete_folder(str(folder_path))
        if success:
            print(f"  SUCCESS: {folder_path}")
        else:
            print(
                f"  FAILED: {folder_path}"
            )  # _delete_folder already prints error details
    print("--- Deletion Process Complete ---")

    # --- Write Metadata Files ---
    os.makedirs(output_dir, exist_ok=True)

    # symlinks.txt
    # format:
    # mode,uid,gid,'path/to/link','path/to/target'
    # ex: 0777,1000,1000,'path/to/link','path/to/target'
    # NOTE: mode is always 0777.
    symlink_list = []
    for d_path in symlinks_for_metadata:  # Iterate over Path objects
        # d_path is a Path object, but _path_stat and _encapsulate expect strings
        symlink_target_path = os.readlink(os.path.join(target_dir, str(d_path)))
        symlink_entry = (
            f"{_join_mode_uid_gid(target_dir, str(d_path))},"
            f"{_encapsulate(str(d_path), prefix=prefix)},"
            f"{_encapsulate(symlink_target_path)}"
        )
        symlink_list.append(symlink_entry)
    with open(os.path.join(output_dir, symlink_file), "w") as _f:
        _f.writelines("\n".join(symlink_list))

    # dirs.txt
    # format:
    # mode,uid,gid,'dir/name'
    # ex: 0755,1000,1000,'path/to/dir'
    with open(os.path.join(output_dir, directory_file), "w") as _f:
        dirs_list = [
            f"{_join_mode_uid_gid(target_dir, str(d_path))},{_encapsulate(str(d_path), prefix=prefix)}"
            # Path object to string
            for d_path in dirs_for_metadata
        ]
        _f.writelines("\n".join(dirs_list))

    # compression with zstd
    #   store the compressed file with its original file's hash and .zstd ext as name,
    #   directly under the <compressed_dir>
    cctx = None  # Initialize cctx to None
    if compressed_dir:
        os.makedirs(compressed_dir, exist_ok=True)
        cctx = zstandard.ZstdCompressor(
            level=ZSTD_COMPRESSION_LEVEL, threads=ZSTD_MULTITHREADS
        )

    # regulars.txt
    # format:
    # mode,uid,gid,link number,sha256sum,'path/to/file',size,inode,[compress_alg]
    # ex: 0644,1000,1000,1,0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef,'path/to/file',1234,12345678,[zst]
    total_regular_size = 0

    with open(os.path.join(output_dir, regular_file), "w") as _f:

        regular_list = []
        for d_path in regulars_for_metadata:  # Iterate over Path objects
            # Convert Path objects to strings for original functions
            size = os.path.getsize(os.path.join(target_dir, str(d_path)))
            stat = os.stat(os.path.join(target_dir, str(d_path)))
            nlink = stat.st_nlink
            inode = stat.st_ino if nlink > 1 else ""
            sha256hash = _file_sha256(
                os.path.join(target_dir, str(d_path))
            )  # Path object to string

            # if compression is enabled, try to compress the file here
            compress_alg = ""
            if compressed_dir and cctx:  # Check if cctx is not None
                src_f = os.path.join(target_dir, str(d_path))
                dst_f = os.path.join(
                    compressed_dir, f"{sha256hash}.{ZSTD_COMPRESSION_EXTENSION}"
                )  # add zstd extension to filename
                # NOTE: skip already compressed file
                if os.path.exists(dst_f) or zstd_compress_file(
                    cctx,  # type: ignore
                    src_f,
                    dst_f,
                    cmpr_ratio=cmpr_ratio,
                    filesize_threshold=filesize_threshold,
                ):
                    compress_alg = ZSTD_COMPRESSION_EXTENSION

            regular_list.append(
                f"{_join_mode_uid_gid(target_dir, str(d_path), nlink=True)},"  # Path object to string
                f"{sha256hash},"
                f"{_encapsulate(str(d_path), prefix=prefix)},"  # Path object to string
                f"{size},"
                f"{inode},"
                f"{compress_alg}"  # ensure the compress_alg is at the end
            )
            total_regular_size += size
        _f.writelines("\n".join(regular_list))

    with open(os.path.join(output_dir, total_regular_size_file), "w") as _f:
        _f.write(str(total_regular_size))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--target-dir", help="target directory.", required=True)
    parser.add_argument(
        "--compressed-dir", help="the directory to save compressed file."
    )
    parser.add_argument(
        "--compress-ratio",
        help="compression ratio threshold",
        default=1.25,  # uncompressed/compressed = 1.25
        type=float,
    )
    parser.add_argument(
        "--compress-filesize",
        help="lower bound size of file to be compressed",
        default=16 * 1024,  # 16KiB
        type=int,
    )
    parser.add_argument("--prefix", help="file name prefix.", default="/")
    parser.add_argument("--output-dir", help="metadata output directory.", default=".")
    parser.add_argument(
        "--directory-file", help="directory meta data.", default="dirs.txt"
    )
    parser.add_argument(
        "--symlink-file", help="symbolic link meta data.", default="symlinks.txt"
    )
    parser.add_argument(
        "--regular-file", help="regular file meta data.", default="regulars.txt"
    )
    parser.add_argument(
        "--total-regular-size-file",
        help="total regular file size.",
        default="total_regular_size.txt",
    )
    parser.add_argument(
        "--ignore-file",
        help="ignore file. file format is .gitignore.",
        default="ignore.txt",
    )
    args = parser.parse_args()
    gen_metadata(
        args.target_dir,
        args.compressed_dir,
        args.prefix,
        args.output_dir,
        directory_file=args.directory_file,
        symlink_file=args.symlink_file,
        regular_file=args.regular_file,
        total_regular_size_file=args.total_regular_size_file,
        ignore_file=args.ignore_file,
        cmpr_ratio=args.compress_ratio,
        filesize_threshold=args.compress_filesize,
    )
