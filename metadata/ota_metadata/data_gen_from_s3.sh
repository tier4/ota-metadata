#!/usr/bin/env bash

set -eu

usage() {
    echo "Usage: $0 s3_url [src_dir]"
    exit 1
}

if [ $# -eq 0 ] || [ $# -gt 2 ]; then
    usage
fi
s3_url=${1%/} # remove tailing '/'
echo "s3_url: ${s3_url}"

if [ $# -eq 2 ]; then
    has_src_dir=1
    src_dir=$2
else
    has_src_dir=0
    src_dir=$(mktemp -d)
fi

sudo python3 data_gen.py --help > /dev/null # check runtime error before hand

dst_dir=$(mktemp -du)
echo src_dir=${src_dir}, dst_dir=${dst_dir}
#trap 'rm -rf ${src_dir} ${dst_dir}' EXIT INT ERR

if [ ${has_src_dir} -eq 0 ]; then
    aws s3 cp "${s3_url}/metadata.jwt" ${src_dir}
    aws s3 sync ${s3_url} ${src_dir}
fi

metadata=$(cat ${src_dir}/metadata.jwt)
jwt=(${metadata//./ }) # split by '.'
body=$(echo ${jwt[1]} | base64 -d)
directory=$(echo ${body} | jq -r '.[] | select(.directory)|.directory')
symboliclink=$(echo ${body} | jq -r '.[] | select(.symboliclink)|.symboliclink')
regular=$(echo ${body} | jq -r '.[] | select(.regular)|.regular')
rootfs_directory=$(echo ${body} | jq -r '.[] | select(.rootfs_directory)|.rootfs_directory')

echo "directory ${directory}, symboliclink ${symboliclink}, regular ${regular}, rootfs_directory ${rootfs_directory}"
sudo python3 data_gen.py --dst-dir ${dst_dir} --src-dir ${src_dir}/${rootfs_directory} --directory-file ${src_dir}/${directory} --symlink-file ${src_dir}/${symboliclink} --regular-file ${src_dir}/${regular} --progress

update_image_tar_gz=$(pwd)/update_image.tar.gz
(cd ${dst_dir} && sudo tar zcf ${update_image_tar_gz} *)
