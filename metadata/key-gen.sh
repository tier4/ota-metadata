#!/bin/bash
set -e

openssl ecparam -out privatekey.pem -name prime256v1 -genkey
openssl req -new -x509 \
    -days $((365 * 20 + 5)) \
    -key privatekey.pem \
    -out certificate.pem \
    -sha256 \
    -subj "/C=JP/ST=Tokyo/O=Tier4/CN=ota.example.tier4.jp"
