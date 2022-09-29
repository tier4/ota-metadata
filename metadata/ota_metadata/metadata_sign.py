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


#!/usr/bin/env python3
from os.path import basename, isfile
from hashlib import sha256
import base64
import argparse
import json
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec


def _file_sha256(filename):
    with open(filename, "rb") as f:
        digest = sha256(f.read()).hexdigest()
        return digest


def urlsafe_b64encode(data):
    if type(data) is str:
        data = data.encode()
    return base64.urlsafe_b64encode(data).decode()


def gen_header():
    return urlsafe_b64encode(json.dumps({"alg": "ES256"}))


def gen_payload(
    directory_file,
    symlink_file,
    regular_file,
    persistent_file,
    rootfs_directory,
    certificate_file,
    total_regular_size_file,
):
    payload = [
        {"version": 1},
        {"directory": basename(directory_file), "hash": _file_sha256(directory_file)},
        {"symboliclink": basename(symlink_file), "hash": _file_sha256(symlink_file)},
        {"regular": basename(regular_file), "hash": _file_sha256(regular_file)},
        {
            "persistent": basename(persistent_file),
            "hash": _file_sha256(persistent_file),
        },
        {"rootfs_directory": rootfs_directory},
        {
            "certificate": basename(certificate_file),
            "hash": _file_sha256(certificate_file),
        },
    ]
    if isfile(total_regular_size_file):
        total_regular_size = open(total_regular_size_file).read()
        payload.append({"total_regular_size": total_regular_size})
    return urlsafe_b64encode(json.dumps(payload))


def sign(sign_key_file, data):
    with open(sign_key_file, "rb") as f:
        priv = serialization.load_pem_private_key(f.read(), password=None)
    return urlsafe_b64encode(priv.sign(data.encode(), ec.ECDSA(hashes.SHA256())))


def sign_metadata(
    directory_file,
    symlink_file,
    regular_file,
    persistent_file,
    rootfs_directory,
    sign_key_file,
    cert_file,
    total_regular_size_file,
    output_file,
):
    header = gen_header()
    payload = gen_payload(
        directory_file,
        symlink_file,
        regular_file,
        persistent_file,
        rootfs_directory,
        cert_file,
        total_regular_size_file,
    )
    signature = sign(sign_key_file, f"{header}.{payload}")
    with open(output_file, "w") as f:
        f.write(f"{header}.{payload}.{signature}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sign-key", help="sign key.", required=True)
    parser.add_argument("--cert-file", help="certificate file.", required=True)
    parser.add_argument("--output", help="output file name.", default="metadata.jwt")
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
        "--rootfs-directory", help="rootfs directory.", default="rootfs"
    )
    parser.add_argument(
        "--persistent-file", help="persistent file meta data.", required=True
    )
    parser.add_argument(
        "--total-regular-size-file",
        help="total regular file size.",
        default="total_regular_size.txt",
    )
    args = parser.parse_args()
    sign_metadata(
        directory_file=args.directory_file,
        symlink_file=args.symlink_file,
        regular_file=args.regular_file,
        persistent_file=args.persistent_file,
        rootfs_directory=args.rootfs_directory,
        sign_key_file=args.sign_key,
        cert_file=args.cert_file,
        total_regular_size_file=args.total_regular_size_file,
        output_file=args.output,
    )
