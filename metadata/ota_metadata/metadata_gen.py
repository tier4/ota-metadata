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
import zstandard
import igittigitt
from hashlib import sha256
from pathlib import Path
from packaging import version
from functools import cmp_to_key

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
    ONE_MB = 1048576
    with open(filename, "rb") as f:
        m = sha256()
        while True:
            d = f.read(ONE_MB)
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
    parser = igittigitt.IgnoreParser()
    with open(ignore_file) as f:
        for line in f:
            line = line.rstrip("\n")
            parser.add_rule(line, base_path=target_dir)
    return parser


def _get_latest_kernel_version(boot_dir: Path):
    kfiles_path = str(boot_dir / "vmlinuz-*.*.*-*-*")

    pa = re.compile(r"vmlinuz-(?P<version>\d+\.\d+\.\d+-\d+)(?P<suffix>.*)")

    def compare(left, right):
        ma_l = pa.match(Path(left).name)
        ma_r = pa.match(Path(right).name)
        ver_l = version.parse(ma_l["version"])
        ver_r = version.parse(ma_r["version"])
        return 1 if ver_l > ver_r else -1

    kfile_glob = [f for f in glob.glob(kfiles_path) if not Path(f).is_symlink()]
    kfiles = sorted(kfile_glob, key=cmp_to_key(compare), reverse=True)

    return Path(kfiles[0])  # latest


def _list_non_latest_kernels(boot_dir: Path):
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
    check_patterns = [r"home/autoware/[^/]+/build", r"home/autoware/[^/]+/src"]

    # This is the flag to control if we will check and add files back to "build" and "src" folder
    check_symlink = any(
        bool(re.search(pattern, str(rule)))
        for rule in ignore.rules
        for pattern in check_patterns
    )

    # Special Patterns that we need to check and add files.
    build_folder_patterns = [
        r"home/autoware/[^/]*/build/.*/hook/.*",
        r"home/autoware/[^/]*/build/.*/.*.egg-info/.*",
    ]

    additional_symlink_set = set()
    additional_regular_set = set()
    additional_dir_set = set()

    # remove kernels under /boot directory other than latest
    non_latest_kernels = _list_non_latest_kernels(p / "boot")
    dirs = []
    symlinks = []
    regulars = []
    for f in p.glob("**/*"):
        try:
            if ignore.match(target_abs / str(f.relative_to(target_dir))):
                if check_symlink:
                    relative_path = str(f.relative_to(target_dir))
                    if any(
                        re.search(pattern, relative_path) for pattern in check_patterns
                    ):
                        if f.is_dir() and not f.is_symlink():
                            additional_dir_set.add(relative_path)
                        elif f.is_symlink():
                            additional_symlink_set.add(relative_path)
                        elif f.is_file() and not f.is_symlink():
                            if any(
                                re.search(file_pattern, relative_path)
                                for file_pattern in build_folder_patterns
                            ):
                                additional_regular_set.add(relative_path)
                continue
            if str(f) in non_latest_kernels:
                print(f"INFO: {f} is not a latest kernel. skip.")
                continue
        except Exception as e:
            if str(e).startswith("Symlink loop from"):
                print(f"WARN: {e}")
            else:
                raise
        if f.is_dir() and not f.is_symlink():
            dirs.append(str(f.relative_to(target_dir)))
        if f.is_symlink():
            symlinks.append(str(f.relative_to(target_dir)))
        if f.is_file() and not f.is_symlink():
            regulars.append(str(f.relative_to(target_dir)))

    # symlinks.txt
    # format:
    # mode,uid,gid,'path/to/link','path/to/target'
    # ex: 0777,1000,1000,'path/to/link','path/to/target'
    # NOTE: mode is always 0777.
    symlink_list = []

    if check_symlink:
        symlinks.extend(additional_symlink_set)

    for d in symlinks:

        symlink_target_path = os.readlink(os.path.join(target_dir, d))
        symlink_entry = (
            f"{_join_mode_uid_gid(target_dir, d)},"
            f"{_encapsulate(d, prefix=prefix)},"
            f"{_encapsulate(symlink_target_path)}"
        )
        symlink_list.append(symlink_entry)

        # Do nothing if ignore file does not have the following paths defined
        # "home/autoware/*build" or "home/autoware/*/src" definition
        if check_symlink is False:
            continue

        # Check the symlink target file
        # if they are under "home/autoware/*/build" or "home/autoware/*/src"

        # when the target link is defined as "/link1/link2/link3"
        if symlink_target_path.startswith("/"):
            target_path_abs = os.path.normpath(str(target_abs) + symlink_target_path)
            symlink_target_path = symlink_target_path[1:]
        # when the target link is defined as "link1/link2/link3" or "../link4" or "../../link5"
        else:
            # start to get symlink file's absolute path
            current_path = os.path.dirname((os.path.join(target_abs, d)))
            target_path_abs = os.path.normpath(
                os.path.join(current_path, symlink_target_path)
            )
            # reformat the symlink target link to "/link1/link2/link3"
            symlink_target_path = os.path.relpath(target_path_abs, target_dir)

        # In case the target link matches the ignore patten,
        # we need to check and add it back to regulars[] and dirs[]
        # Also, we need to the path level one by one.
        # In case the target link is a symlink, we will ignore it.
        if ignore.match(Path(target_path_abs)):
            path_names = symlink_target_path.split(os.sep)
            path_to_check = target_dir
            for path_name in path_names:
                if path_name:
                    path_to_check = os.path.join(path_to_check, path_name)
                    if os.path.islink(path_to_check):
                        break
                    elif os.path.isdir(path_to_check):
                        additional_dir_set.add(
                            os.path.relpath(path_to_check, target_dir)
                        )
                    elif os.path.isfile(path_to_check):
                        additional_regular_set.add(
                            os.path.relpath(path_to_check, target_dir)
                        )

    with open(os.path.join(output_dir, symlink_file), "w") as _f:
        _f.writelines("\n".join(symlink_list))

    # Add additional files and directories here.
    # Important to check check_symlink.
    # Make sure not affect the current behavior.
    if check_symlink:
        dirs.extend(additional_dir_set)
        regulars.extend(additional_regular_set)
        dirs = list(set(dirs))
        regulars = list(set(regulars))

    # dirs.txt
    # format:
    # mode,uid,gid,'dir/name'
    # ex: 0755,1000,1000,'path/to/dir'
    with open(os.path.join(output_dir, directory_file), "w") as _f:
        dirs_list = [
            f"{_join_mode_uid_gid(target_dir, d)},{_encapsulate(d, prefix=prefix)}"
            for d in dirs
        ]
        _f.writelines("\n".join(dirs_list))

    # compression with zstd
    #   store the compressed file with its original file's hash and .zstd ext as name,
    #   directly under the <compressed_dir>
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
        for d in regulars:
            size = os.path.getsize(os.path.join(target_dir, d))
            stat = os.stat(os.path.join(target_dir, d))
            nlink = stat.st_nlink
            inode = stat.st_ino if nlink > 1 else ""
            sha256hash = _file_sha256(os.path.join(target_dir, d))

            # if compression is enabled, try to compress the file here
            compress_alg = ""
            if compressed_dir:
                src_f = os.path.join(target_dir, d)
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
                f"{_join_mode_uid_gid(target_dir, d, nlink=True)},"
                f"{sha256hash},"
                f"{_encapsulate(d, prefix=prefix)},"
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
