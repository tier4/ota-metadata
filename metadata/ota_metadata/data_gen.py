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
import shutil
from hashlib import sha256
import argparse
import re
from pathlib import Path
from tqdm import tqdm


def _file_sha256(filename):
    with open(filename, "rb") as f:
        digest = sha256(f.read()).hexdigest()
        return digest


class _BaseInf:
    _base_pattern = re.compile(
        r"(?P<mode>\d+),(?P<uid>\d+),(?P<gid>\d+),(?P<left_over>.*)"
    )

    @staticmethod
    def de_escape(s: str) -> str:
        return s.replace(r"'\''", r"'")

    def __init__(self, info: str):
        match_res: re.Match = self._base_pattern.match(info.strip("\n"))
        assert match_res is not None
        self.mode = int(match_res.group("mode"), 8)
        self.uid = int(match_res.group("uid"))
        self.gid = int(match_res.group("gid"))

        self._left: str = match_res.group("left_over")


class DirectoryInf(_BaseInf):
    """
    Directory file information class
    """

    def __init__(self, info):
        super().__init__(info)
        self.path = Path(self.de_escape(self._left[1:-1]))


class SymbolicLinkInf(_BaseInf):
    """
    Symbolik link information class
    """

    _pattern = re.compile(r"'(?P<link>.+)((?<!\')',')(?P<target>.+)'")

    def __init__(self, info):
        super().__init__(info)
        res = self._pattern.match(self._left)
        assert res is not None
        self.slink = Path(self.de_escape(res.group("link")))
        self.srcpath = Path(self.de_escape(res.group("target")))


class RegularInf(_BaseInf):
    """
    Regular file information class
    """

    _pattern = re.compile(
        r"(?P<nlink>\d+),(?P<hash>\w+),'(?P<path>.+)'"
        r"(,(?P<size>\d+)?(,(?P<inode>\d+)?(,(?P<compressed_alg>\w+)?)?)?)?"
    )

    def __init__(self, info):
        super().__init__(info)

        res = self._pattern.match(self._left)
        assert res is not None
        self.nlink = int(res.group("nlink"))
        self.sha256hash = res.group("hash")
        self.path = Path(self.de_escape(res.group("path")))
        # make sure that size might be None
        size = res.group("size")
        self.size = None if size is None else int(size)
        self.inode = res.group("inode")
        self.compressed_alg = res.group("compressed_alg")


def _gen_dirs(dst_dir, directory_file, progress):
    with open(directory_file) as f:
        lines = f.read().splitlines()
        for line in tqdm(lines) if progress else lines:
            inf = DirectoryInf(line)
            target_path = f"{dst_dir}{inf.path}"
            os.makedirs(target_path, mode=inf.mode)
            os.chown(target_path, inf.uid, inf.gid)
            os.chmod(target_path, inf.mode)


def _gen_symlinks(dst_dir, symlink_file, progress):
    with open(symlink_file) as f:
        lines = f.read().splitlines()
        for line in tqdm(lines) if progress else lines:
            inf = SymbolicLinkInf(line)
            target_path = f"{dst_dir}{inf.slink}"
            os.symlink(inf.srcpath, target_path)
            os.chown(target_path, inf.uid, inf.gid, follow_symlinks=False)
            # NOTE: symlink file mode is always 0777 for linux system


def _gen_regulars(dst_dir, regular_file, src_dir, progress):
    with open(regular_file) as f:
        lines = f.read().splitlines()
        links_dict = {}
        for line in tqdm(lines) if progress else lines:
            inf = RegularInf(line)
            links_key = inf.inode if inf.inode is not None else inf.sha256hash
            dst = f"{dst_dir}{inf.path}"
            if links_key not in links_dict:
                src = f"{src_dir}{inf.path}"
                shutil.copyfile(src, dst, follow_symlinks=False)
                os.chown(dst, inf.uid, inf.gid)
                os.chmod(dst, inf.mode)
                if inf.nlink >= 2:
                    links_dict.setdefault(links_key, dst)
            else:
                src = links_dict[links_key]
                os.link(src, dst, follow_symlinks=False)


def gen_data(
    dst_dir,
    src_dir,
    directory_file,
    symlink_file,
    regular_file,
    progress,
):
    dst_dir_norm = os.path.normpath(dst_dir)
    src_dir_norm = os.path.normpath(src_dir)
    if dst_dir_norm == src_dir_norm:
        raise ValueError(f"dst({dst_dir_norm}) and src({src_dir_norm}) are same!")
    # mkdir dst
    os.makedirs(dst_dir_norm, exist_ok=True)
    if len(os.listdir(dst_dir_norm)) != 0:
        raise ValueError(f"dst({dst_dir_norm}) is not empty dir.")
    _gen_dirs(dst_dir_norm, directory_file, progress)
    _gen_symlinks(dst_dir_norm, symlink_file, progress)
    _gen_regulars(dst_dir_norm, regular_file, src_dir_norm, progress)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dst-dir", help="destination directory.", required=True)
    parser.add_argument("--src-dir", help="source directory.", required=True)
    parser.add_argument("--progress", help="show progress.", action="store_true")
    parser.add_argument(
        "--directory-file", help="directory meta data.", default="dirs.txt"
    )
    parser.add_argument(
        "--symlink-file", help="symbolic link meta data.", default="symlinks.txt"
    )
    parser.add_argument(
        "--regular-file", help="regular file meta data.", default="regulars.txt"
    )
    args = parser.parse_args()
    gen_data(
        args.dst_dir,
        args.src_dir,
        directory_file=args.directory_file,
        symlink_file=args.symlink_file,
        regular_file=args.regular_file,
        progress=args.progress,
    )
