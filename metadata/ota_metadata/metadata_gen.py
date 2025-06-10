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


import os
import re
import glob
import argparse
import shutil

import zstandard
import igittigitt
from hashlib import sha256
from pathlib import Path
from packaging import version
from functools import cmp_to_key
from typing import Set, List, Optional  # Added for type hinting

ZSTD_COMPRESSION_EXTENSION = "zst"
ZSTD_COMPRESSION_LEVEL = 10
ZSTD_MULTITHREADS = 2
CHUNK_SIZE = 4 * (1024 ** 2)  # 4MiB


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


def _file_sha256(filename: Path) -> str:
    ONE_MB = 1048576
    with open(filename, "rb") as f:
        m = sha256()
        while True:
            d = f.read(ONE_MB)
            if d == b"":
                break
            m.update(d)
        return m.hexdigest()


def _is_regular(path):  # This function is not used in the provided code, can be removed
    return os.path.isfile(path) and not os.path.islink(path)


def _encapsulate(name: str, prefix: str = "") -> str:
    escaped = name.replace("'", "'\\''")
    return f"'{os.path.join(prefix, escaped)}'"


def _decapsulate(name):  # This function is not used in the provided code, can be removed
    return name[1:-1].replace("'\\''", "'")


def _path_stat(base: str, path: str):
    return os.lstat(os.path.join(base, path))  # NOTE: lstat doesn't follow symlink


# return array of mode, uid and gid
def _path_mode_uid_gid(base: str, path: str, nlink: bool = False) -> List[str]:
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


def _join_mode_uid_gid(base: str, path: str, nlink: bool = False) -> str:
    return ",".join(_path_mode_uid_gid(base, path, nlink=nlink))


def ignore_rules(target_dir: str, ignore_file: str) -> igittigitt.IgnoreParser:
    parser = igittigitt.IgnoreParser()
    try:
        with open(ignore_file) as f:
            for line in f:
                line = line.rstrip("\n")
                parser.add_rule(line, base_path=target_dir)
    except FileNotFoundError:
        print(f"Warning: Ignore file '{ignore_file}' not found. No files will be ignored based on rules.")
    return parser


def _delete_file(path: str) -> bool:
    """
    Delete a file at the given path.
    Returns True if the file was deleted, False if exception occurred.
    """
    try:
        file_path = Path(path)
        if file_path.exists() and file_path.is_file():  # Check before deleting
            file_path.unlink()
            print(f"Deleted file: {path}")
            return True
        return False  # File didn't exist or wasn't a file
    except Exception as e:
        print(f"Error deleting file {path}: {e}")
        return False


def _delete_folder(path: str) -> bool:
    """
    Delete a folder at the given path.
    Returns True if the folder was deleted, False if exception occurred.
    """
    try:
        folder_path = Path(path)
        if folder_path.exists() and folder_path.is_dir():  # Check before deleting
            shutil.rmtree(folder_path)
            print(f"Deleted folder: {path}")
            return True
        return False  # Folder didn't exist or wasn't a directory
    except FileNotFoundError:
        print(f"Error: Directory {path} not found.")
        return False
    except PermissionError:
        print(f"Error: Permission denied to delete {path}.")
        return False
    except Exception as e:
        print(f"Error deleting folder {path}: {e}")
        return False


def _get_latest_kernel_version(boot_dir: Path) -> Path:
    kfiles_path = str(boot_dir / "vmlinuz-*.*.*-*-*")

    pa = re.compile(r"vmlinuz-(?P<version>\d+\.\d+\.\d+-\d+)(?P<suffix>.*)")

    def compare(left, right):
        ma_l = pa.match(Path(left).name)
        ma_r = pa.match(Path(right).name)
        # Handle cases where regex might not match (though it should with glob pattern)
        if not ma_l or not ma_r:
            return 0  # Treat as equal if versions can't be parsed
        ver_l = version.parse(ma_l["version"])
        ver_r = version.parse(ma_r["version"])
        return 1 if ver_l > ver_r else -1 if ver_l < ver_r else 0

    # Ensure glob returns non-symlinks, as _list_non_latest_kernels expects that
    kfile_glob = [f for f in glob.glob(kfiles_path) if not Path(f).is_symlink()]
    if not kfile_glob:
        raise Exception(f"No kernel files found in {boot_dir} matching pattern.")
    kfiles = sorted(kfile_glob, key=cmp_to_key(compare), reverse=True)

    return Path(kfiles[0])  # latest


def _list_non_latest_kernels(boot_dir: Path) -> Set[Path]:
    non_latest_kernels: Set[Path] = set()

    # if boot/extlinux/extlinux.conf exists, the kernel is specified in that file
    # so we don't need to pickup the latest kernel, and thus, don't remove any.
    if (boot_dir / "extlinux" / "extlinux.conf").is_file():
        return non_latest_kernels  # Return empty set, no kernels to delete

    pa = re.compile(r"vmlinuz-(?P<version>\d+\.\d+\.\d+-\d+)(?P<suffix>.*)")

    try:
        vmlinuz_latest = _get_latest_kernel_version(boot_dir)
        k_ma = pa.match(vmlinuz_latest.name)
        if not k_ma:
            raise Exception(f"Could not parse version from latest kernel file: {vmlinuz_latest.name}")

        ver = k_ma["version"]
        suf = k_ma["suffix"]
        initrd_img_latest = vmlinuz_latest.parent / f"initrd.img-{ver}{suf}"
        system_map_latest = vmlinuz_latest.parent / f"System.map-{ver}{suf}"
        config_latest = vmlinuz_latest.parent / f"config-{ver}{suf}"

        # Collect all relevant files that are not symlinks
        all_kernel_files = {Path(f) for f in glob.glob(str(boot_dir / "vmlinuz-*")) if not Path(f).is_symlink()}
        all_initrd_files = {Path(f) for f in glob.glob(str(boot_dir / "initrd.img-*")) if not Path(f).is_symlink()}
        all_system_map_files = {Path(f) for f in glob.glob(str(boot_dir / "System.map-*")) if not Path(f).is_symlink()}
        all_config_files = {Path(f) for f in glob.glob(str(boot_dir / "config-*")) if not Path(f).is_symlink()}

        if initrd_img_latest not in all_initrd_files:
            raise Exception(f"{initrd_img_latest} (initrd for latest kernel) doesn't exist.")

        # Add all currently found files to the set of non_latest_kernels
        non_latest_kernels.update(all_kernel_files)
        non_latest_kernels.update(all_initrd_files)
        non_latest_kernels.update(all_system_map_files)
        non_latest_kernels.update(all_config_files)

        # Remove the latest kernel's components from the set
        non_latest_kernels.discard(vmlinuz_latest)
        non_latest_kernels.discard(initrd_img_latest)
        non_latest_kernels.discard(system_map_latest)  # Optional, may not exist
        non_latest_kernels.discard(config_latest)  # Optional, may not exist

    except Exception as e:
        print(f"Warning: Could not determine non-latest kernels due to error: {e}. Skipping kernel exclusion.")
        return set()  # Return empty set if an error occurs

    return non_latest_kernels


def gen_metadata(
        target_dir: str,
        compressed_dir: Optional[str],
        prefix: str,
        output_dir: str,
        directory_file: str,
        symlink_file: str,
        regular_file: str,
        total_regular_size_file: str,
        ignore_file: str,
        *,
        cmpr_ratio: float,
        filesize_threshold: int,
):
    p = Path(target_dir)
    target_abs = Path(os.path.abspath(target_dir))
    ignore = ignore_rules(target_dir, ignore_file)

    check_patterns = [
        re.compile(r"home/autoware/[^/]+/build"),
        re.compile(r"home/autoware/[^/]+/src"),
    ]
    build_folder_patterns = [
        re.compile(r"home/autoware/[^/]*/build/.*/hook/.*"),
        re.compile(r"home/autoware/[^/]*/build/.*/.*.egg-info/.*"),
        re.compile(r"home/autoware/[^/]*/build/.*/.*.so$"),
    ]

    # Determine if special symlink checking logic for 'build'/'src' is needed
    check_symlink_special_case = any(
        _pattern.search(str(_rule))
        for _rule in ignore.rules
        for _pattern in check_patterns
    )

    # Sets to collect paths for metadata (what we keep)
    metadata_dirs: Set[Path] = set()
    metadata_symlinks: Set[Path] = set()
    metadata_regulars: Set[Path] = set()

    # Set to store absolute paths for deletion candidates
    paths_to_delete_abs: Set[Path] = set()

    # Identify non-latest kernels (absolute paths)
    non_latest_kernels_abs = _list_non_latest_kernels(p / "boot")

    # First Pass: Categorize and identify deletion candidates
    # We iterate all paths and decide if they should be in metadata or deleted.
    for f_abs in p.glob("**/*"):
        try:
            # Skip symlink loops
            if f_abs.is_symlink() and not f_abs.exists():  # broken symlink
                print(f"WARN: Broken symlink detected: {f_abs}. Skipping.")
                continue

            f_rel = f_abs.relative_to(target_dir)

            is_ignored = ignore.match(target_abs / str(f_rel))  # Match using absolute path of relative
            is_symlink = f_abs.is_symlink()
            is_non_latest_kernel = f_abs in non_latest_kernels_abs

            # Symlinks are never deleted. They are always added to metadata for reconstruction.
            if is_symlink:
                metadata_symlinks.add(f_rel)
                continue  # Skip to next file, symlinks are handled

            # --- Decision Logic for Files/Directories (non-symlinks) ---
            should_be_deleted = False

            if is_non_latest_kernel:
                # Non-latest kernels (non-symlinks) are always marked for deletion
                should_be_deleted = True
            elif is_ignored:
                # If ignored, check if it's a special case that should be kept despite ignore rules
                should_be_kept_despite_ignore = False
                if check_symlink_special_case:
                    # Check if the path itself is one of the special 'autoware/build' or 'autoware/src' paths
                    is_in_special_autoware_pattern = any(pattern.search(str(f_rel)) for pattern in check_patterns)

                    if is_in_special_autoware_pattern:
                        if f_abs.is_dir():
                            # Keep directories in special autoware patterns (e.g., home/autoware/*/build itself)
                            should_be_kept_despite_ignore = True
                        elif f_abs.is_file():
                            # Keep specific file types within special autoware build patterns
                            is_special_build_file_type = any(
                                _file_pattern.search(str(f_rel)) for _file_pattern in build_folder_patterns)
                            if is_special_build_file_type:
                                should_be_kept_despite_ignore = True

                if not should_be_kept_despite_ignore:
                    # If ignored and not a special case to keep, then mark for deletion
                    should_be_deleted = True

            if should_be_deleted:
                paths_to_delete_abs.add(f_abs)
            else:
                # If not marked for deletion, add to metadata lists
                if f_abs.is_dir():
                    metadata_dirs.add(f_rel)
                elif f_abs.is_file():
                    metadata_regulars.add(f_rel)

        except Exception as e:
            if str(e).startswith("Symlink loop from"):
                print(f"WARN: {e}")
            else:
                print(f"Error processing path {f_abs}: {e}. Skipping.")
                continue  # Skip this file and continue with others

    # Second Pass: Process symlink targets for inclusion in metadata
    # This ensures that files/dirs that are targets of symlinks are included
    # in metadata even if they were initially ignored.
    symlink_targets_for_metadata: Set[Path] = set()
    for symlink_rel_path in metadata_symlinks:  # Iterate through symlinks we've decided to keep
        try:
            symlink_abs_path = p / symlink_rel_path
            symlink_target_raw = os.readlink(str(symlink_abs_path))  # target as string

            # Resolve the absolute path of the symlink target
            if Path(symlink_target_raw).is_absolute():
                target_abs_path = Path(target_abs.root) / symlink_target_raw.lstrip(os.sep)
            else:
                target_abs_path = (symlink_abs_path.parent / symlink_target_raw).resolve()

            # Only process if the target is actually within the target_dir
            if target_abs_path.is_relative_to(target_abs):
                target_rel_path = target_abs_path.relative_to(target_dir)

                # If this target (which is within target_dir) was previously marked for deletion
                # or was ignored, we now re-include it because a symlink points to it.
                if target_abs_path in paths_to_delete_abs:
                    # Remove it from deletion candidates
                    paths_to_delete_abs.discard(target_abs_path)

                # Add the target and its parent directories (up to the ignored root) to metadata
                # if it falls under special check patterns.
                if check_symlink_special_case and ignore.match(target_abs_path):
                    parts = target_rel_path.parts
                    current_partial_path = Path()
                    for part in parts:
                        if part:
                            current_partial_path /= part
                            full_checked_path_abs = target_dir / current_partial_path

                            if full_checked_path_abs.is_symlink():
                                # Stop if a symlink is encountered in the path to target
                                break
                            if any(pattern.search(str(current_partial_path)) for pattern in check_patterns):
                                symlink_targets_for_metadata.add(current_partial_path)
                                # If it was a file/dir, ensure it's not in deletion candidates
                                if full_checked_path_abs in paths_to_delete_abs:
                                    paths_to_delete_abs.discard(full_checked_path_abs)
            else:
                print(
                    f"INFO: Symlink {symlink_rel_path} targets outside {target_dir}: {symlink_target_raw}. Not including target in metadata.")

        except OSError as e:  # Handle broken symlinks or permission issues during readlink
            print(f"WARN: Failed to read symlink {symlink_rel_path}: {e}. Skipping target processing.")
        except Exception as e:
            print(f"Error processing symlink target for {symlink_rel_path}: {e}. Skipping.")

    # Incorporate the symlink targets into our main metadata lists
    for p_rel in symlink_targets_for_metadata:
        p_abs = p / p_rel
        if p_abs.is_dir():
            metadata_dirs.add(p_rel)
        elif p_abs.is_file():
            metadata_regulars.add(p_rel)

    # Finalize metadata lists (sorted lists from sets)
    dirs_final = sorted(list(metadata_dirs))
    symlinks_final = sorted(list(metadata_symlinks))
    regulars_final = sorted(list(metadata_regulars))

    # --- Perform Deletion ---
    # Sort files to delete by path (longest first) to ensure subdirectories' files are deleted
    # before parent directories are attempted. Path.unlink handles files, shutil.rmtree handles dirs.
    files_to_delete = sorted([p for p in paths_to_delete_abs if p.is_file()], key=lambda x: str(x), reverse=True)
    folders_to_delete = sorted([p for p in paths_to_delete_abs if p.is_dir()], key=lambda x: str(x), reverse=True)

    print("\n--- Deleting ignored/non-latest files and folders ---")
    for file_path in files_to_delete:
        _delete_file(str(file_path))

    for folder_path in folders_to_delete:
        _delete_folder(str(folder_path))
    print("--- Deletion complete ---")

    # --- Write Metadata Files ---
    os.makedirs(output_dir, exist_ok=True)

    # symlinks.txt
    symlink_list = []
    for d in symlinks_final:
        symlink_target_path = os.readlink(os.path.join(target_dir, str(d)))
        symlink_entry = (
            f"{_join_mode_uid_gid(target_dir, str(d))},"
            f"{_encapsulate(str(d), prefix=prefix)},"
            f"{_encapsulate(symlink_target_path)}"
        )
        symlink_list.append(symlink_entry)
    with open(os.path.join(output_dir, symlink_file), "w") as _f:
        _f.writelines("\n".join(symlink_list))

    # dirs.txt
    with open(os.path.join(output_dir, directory_file), "w") as _f:
        dirs_list = [
            f"{_join_mode_uid_gid(target_dir, str(d))},{_encapsulate(str(d), prefix=prefix)}"
            for d in dirs_final
        ]
        _f.writelines("\n".join(dirs_list))

    # compression with zstd
    cctx: Optional[zstandard.ZstdCompressor] = None
    if compressed_dir:
        os.makedirs(compressed_dir, exist_ok=True)
        cctx = zstandard.ZstdCompressor(
            level=ZSTD_COMPRESSION_LEVEL, threads=ZSTD_MULTITHREADS
        )

    # regulars.txt
    total_regular_size = 0
    with open(os.path.join(output_dir, regular_file), "w") as _f:
        regular_list = []
        for d in regulars_final:
            full_file_path = p / d  # Use Path object for _file_sha256
            size = full_file_path.stat().st_size
            stat = full_file_path.stat()
            nlink = stat.st_nlink
            inode = str(stat.st_ino) if nlink > 1 else ""
            sha256hash = _file_sha256(full_file_path)

            # if compression is enabled, try to compress the file here
            compress_alg = ""
            if compressed_dir and cctx:
                src_f = str(full_file_path)
                dst_f = os.path.join(
                    compressed_dir, f"{sha256hash}.{ZSTD_COMPRESSION_EXTENSION}"
                )
                if os.path.exists(dst_f) or zstd_compress_file(
                        cctx,
                        src_f,
                        dst_f,
                        cmpr_ratio=cmpr_ratio,
                        filesize_threshold=filesize_threshold,
                ):
                    compress_alg = ZSTD_COMPRESSION_EXTENSION

            regular_list.append(
                f"{_join_mode_uid_gid(target_dir, str(d), nlink=True)},"
                f"{sha256hash},"
                f"{_encapsulate(str(d), prefix=prefix)},"
                f"{size},"
                f"{inode},"
                f"{compress_alg}"
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