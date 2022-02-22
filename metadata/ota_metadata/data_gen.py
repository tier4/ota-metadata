#!/usr/bin/env python3

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
        r"(?P<nlink>\d+),(?P<hash>\w+),'(?P<path>.+)',?(?P<size>\d+)?"
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


def _gen_dirs(dst_dir, directory_file, progress):
    with open(directory_file) as f:
        lines = f.read().splitlines()
        for l in tqdm(lines) if progress else lines:
            inf = DirectoryInf(l)
            target_path = f"{dst_dir}{inf.path}"
            os.makedirs(target_path, mode=int(inf.mode, 8))
            os.chown(target_path, int(inf.uid), int(inf.gpid))
            os.chmod(target_path, int(inf.mode, 8))


def _gen_symlinks(dst_dir, symlink_file, progress):
    with open(symlink_file) as f:
        lines = f.read().splitlines()
        for l in tqdm(lines) if progress else lines:
            inf = SymbolicLinkInf(l)
            target_path = f"{dst_dir}{inf.slink}"
            os.symlink(inf.srcpath, target_path)
            os.chown(target_path, int(inf.uid), int(inf.gpid), follow_symlinks=False)
            # NOTE: symlink file mode is always 0777 for linux system


def _gen_regulars(dst_dir, regular_file, src_dir, progress):
    with open(regular_file) as f:
        lines = f.read().splitlines()
        links_dict = {}
        for l in tqdm(lines) if progress else lines:
            inf = RegularInf(l)
            dst = f"{dst_dir}{inf.path}"
            if inf.sha256hash not in links_dict:
                src = f"{src_dir}{inf.path}"
                shutil.copyfile(src, dst, follow_symlinks=False)
                os.chown(dst, int(inf.uid), int(inf.gpid))
                os.chmod(dst, int(inf.mode, 8))
                if inf.links >= 2:
                    links_dict.setdefault(inf.sha256hash, dst)
            else:
                src = links_dict[inf.sha256hash]
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
    os.makedirs(dst_dir_norm)  # should not exist.
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
