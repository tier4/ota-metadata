#!/usr/bin/env python3

import os
from hashlib import sha256
import argparse
import pathlib
import igittigitt


def _file_sha256(filename):
    with open(filename, "rb") as f:
        digest = sha256(f.read()).hexdigest()
        return digest


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
    prefix,
    output_dir,
    directory_file,
    symlink_file,
    regular_file,
    ignore_file,
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
            f"{_join_mode_uid_gid(target_dir, d)},{_encapsulate(d, prefix=prefix)},{_encapsulate(os.readlink(os.path.join(target_dir, d)))}"
            for d in symlinks
        ]
        f.writelines("\n".join(symlink_list))

    # regulars.txt
    # format:
    # mode,uid,gid,link number,sha256sum,'path/to/file'
    # ex: 0644,1000,1000,1,0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef,'path/to/file'
    with open(os.path.join(output_dir, regular_file), "w") as f:
        regular_list = [
            f"{_join_mode_uid_gid(target_dir, d, nlink=True)},{_file_sha256(os.path.join(target_dir, d))},{_encapsulate(d, prefix=prefix)}"
            for d in regulars
        ]
        f.writelines("\n".join(regular_list))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-dir", help="target directory.", required=True)
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
        "--ignore-file",
        help="ignore file. file format is .gitignore.",
        default="ignore.txt",
    )
    args = parser.parse_args()
    gen_metadata(
        args.target_dir,
        args.prefix,
        args.output_dir,
        directory_file=args.directory_file,
        symlink_file=args.symlink_file,
        regular_file=args.regular_file,
        ignore_file=args.ignore_file,
    )
