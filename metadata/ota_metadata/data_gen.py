#!/usr/bin/env python3

import os
import shutil
from hashlib import sha256
import argparse
import pathlib
import re
from tqdm import tqdm


def _decapsulate(name):
    return name[1:-1].replace("'\\''", "'")


def _file_sha256(filename):
    with open(filename, "rb") as f:
        digest = sha256(f.read()).hexdigest()
        return digest


def _get_separated_strings(string, search, num):
    arr = []
    curr = 0
    for i in range(num):
        pos = string[curr:].find(search)
        arr.append(string[curr : curr + pos])
        curr += pos + 1
    return arr, curr


def _find_file_separate(string):
    match = re.search(r"','(?!\\'')", string)  # find ',' not followed by \\''
    return match.start()


class DirectoryInf:
    """
    Directory file information class
    """

    def __init__(self, info):
        line = info.replace("\n", "")
        info_list, last = _get_separated_strings(line, ",", 3)
        self.mode = info_list[0]
        self.uid = info_list[1]
        self.gpid = info_list[2]
        self.path = _decapsulate(line[last:])


class SymbolicLinkInf:
    """
    Symbolik link information class
    """

    def __init__(self, info):
        line = info.replace("\n", "")
        info_list, last = _get_separated_strings(line, ",", 3)
        self.mode = info_list[0]
        self.uid = info_list[1]
        self.gpid = info_list[2]
        sep_pos = _find_file_separate(line)
        self.slink = _decapsulate(line[last : sep_pos + 1])
        self.srcpath = _decapsulate(line[sep_pos + 2 :])


class RegularInf:
    """
    Regular file information class
    """

    def __init__(self, info):
        line = info.replace("\n", "")
        info_list, last = _get_separated_strings(line, ",", 5)
        self.mode = info_list[0]
        self.uid = info_list[1]
        self.gpid = info_list[2]
        self.links = int(info_list[3])
        self.sha256hash = info_list[4]
        self.path = _decapsulate(line[last:])


def _gen_dirs(dst_dir, directory_file):
    with open(directory_file) as f:
        for l in tqdm(f.read().splitlines()):
            inf = DirectoryInf(l)
            target_path = f"{dst_dir}{inf.path}"
            os.makedirs(target_path, mode=int(inf.mode, 8))
            os.chown(target_path, int(inf.uid), int(inf.gpid))
            os.chmod(target_path, int(inf.mode, 8))


def _gen_symlinks(dst_dir, symlink_file):
    with open(symlink_file) as f:
        for l in tqdm(f.read().splitlines()):
            inf = SymbolicLinkInf(l)
            target_path = f"{dst_dir}{inf.slink}"
            os.symlink(inf.srcpath, target_path)
            os.chown(target_path, int(inf.uid), int(inf.gpid), follow_symlinks=False)
            # NOTE: symlink file mode is always 0777 for linux system


def _gen_regulars(dst_dir, regular_file, src_dir):
    with open(regular_file) as f:
        for l in tqdm(f.read().splitlines()):
            inf = RegularInf(l)
            src = f"{src_dir}{inf.path}"
            dst = f"{dst_dir}{inf.path}"
            if inf.links >= 2:
                os.link(src, dst, follow_symlinks=False)
            else:
                shutil.copyfile(src, dst, follow_symlinks=False)
            os.chown(dst, int(inf.uid), int(inf.gpid))
            os.chmod(dst, int(inf.mode, 8))


def gen_data(
    dst_dir,
    src_dir,
    directory_file,
    symlink_file,
    regular_file,
):
    dst_dir_norm = os.path.normpath(dst_dir)
    src_dir_norm = os.path.normpath(src_dir)
    if dst_dir_norm == src_dir_norm:
        raise ValueError(f"dst({dst_dir_norm}) and src({src_dir_norm}) are same!")
    # mkdir dst
    os.makedirs(dst_dir_norm)  # should not exist.
    _gen_dirs(dst_dir_norm, directory_file)
    _gen_symlinks(dst_dir_norm, symlink_file)
    _gen_regulars(dst_dir_norm, regular_file, src_dir_norm)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dst-dir", help="destination directory.", required=True)
    parser.add_argument("--src-dir", help="source directory.", required=True)
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
    )
