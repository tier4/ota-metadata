#!/usr/bin/env python3
#
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
import argparse
import pathlib
import zstandard
import igittigitt
from hashlib import sha256

ZSTD_COMPRESSION_ALG = "zstd"
ZSTD_COMPRESSION_LEVEL = 10
ZSTD_MULTITHREADS = 2
CHUNK_SIZE = 4 * (1024**2)  # 4MiB


class ZstdSkipFile(Exception):
    pass


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
    try:
        with open(src_fpath, "rb") as src_f, open(dst_fpath, "wb") as dst_f:
            with cctx.stream_writer(dst_f, size=src_size) as compressor:
                while data := src_f.read(CHUNK_SIZE):
                    compressor.write(data)
        # drop compressed file if cmpr ratio is too small or compressed failed
        if (
            not (compressed_bytes := os.path.getsize(dst_fpath))
            or src_size / compressed_bytes < cmpr_ratio
        ):
            raise ZstdSkipFile
        return True
    except Exception:  # cleanup on failure
        try:
            os.remove(dst_fpath)
        except OSError:
            pass
        return False


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
    p = pathlib.Path(target_dir)
    target_abs = pathlib.Path(os.path.abspath(target_dir))
    ignore = ignore_rules(target_dir, ignore_file)
    dirs = []
    symlinks = []
    regulars = []
    for f in p.glob("**/*"):
        try:
            if ignore.match(target_abs / str(f.relative_to(target_dir))):
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

    # dirs.txt
    # format:
    # mode,uid,gid,'dir/name'
    # ex: 0755,1000,1000,'path/to/dir'
    with open(os.path.join(output_dir, directory_file), "w") as f:
        dirs_list = [
            f"{_join_mode_uid_gid(target_dir, d)},{_encapsulate(d, prefix=prefix)}"
            for d in dirs
        ]
        f.writelines("\n".join(dirs_list))

    # symlinks.txt
    # format:
    # mode,uid,gid,'path/to/link','path/to/target'
    # ex: 0777,1000,1000,'path/to/link','path/to/target'
    # NOTE: mode is always 0777.
    with open(os.path.join(output_dir, symlink_file), "w") as f:
        symlink_list = [
            f"{_join_mode_uid_gid(target_dir, d)},"
            f"{_encapsulate(d, prefix=prefix)},"
            f"{_encapsulate(os.readlink(os.path.join(target_dir, d)))}"
            for d in symlinks
        ]
        f.writelines("\n".join(symlink_list))

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
    # ex: 0644,1000,1000,1,0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef,'path/to/file',1234,12345678,[zstd]
    total_regular_size = 0
    with open(os.path.join(output_dir, regular_file), "w") as f:
        regular_list = []
        for d in regulars:
            size = os.path.getsize(os.path.join(target_dir, d))
            stat = os.stat(os.path.join(target_dir, d))
            nlink = stat.st_nlink
            inode = stat.st_ino if nlink > 1 else ""
            sha256hash = _file_sha256(os.path.join(target_dir, d))

            # if compression is enabled, try to compress the file here
            if compressed_dir and zstd_compress_file(
                cctx,  # type: ignore
                os.path.join(target_dir, d),
                os.path.join(compressed_dir, f"{sha256hash}.{ZSTD_COMPRESSION_ALG}"),
                cmpr_ratio=cmpr_ratio,
                filesize_threshold=filesize_threshold,
            ):
                compress_alg = ZSTD_COMPRESSION_ALG
            else:
                compress_alg = ""

            regular_list.append(
                f"{_join_mode_uid_gid(target_dir, d, nlink=True)},"
                f"{sha256hash},"
                f"{_encapsulate(d, prefix=prefix)},"
                f"{size},"
                f"{inode},"
                f"{compress_alg}"  # ensure the compress_alg is at the end
            )
            total_regular_size += size
        f.writelines("\n".join(regular_list))

    with open(os.path.join(output_dir, total_regular_size_file), "w") as f:
        f.write(str(total_regular_size))


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
