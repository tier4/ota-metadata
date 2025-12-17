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

"""
Test suite for zstandard stream_writer API.

This module tests the stream_writer functionality used in metadata_gen.py
to ensure compatibility with zstandard library version updates.
"""

import pytest
import zstandard


COMPRESSION_LEVEL = 10
MULTI_THREADS = 2
CHUNK_SIZE = 4 * (1024**2)  # 4MiB


@pytest.fixture
def zstd_compressor():
    """Create a ZstdCompressor with production settings."""
    return zstandard.ZstdCompressor(level=COMPRESSION_LEVEL, threads=MULTI_THREADS)


@pytest.fixture
def zstd_decompressor():
    """Create a ZstdDecompressor for verifying compressed data."""
    return zstandard.ZstdDecompressor()


def test_zstd_stream_writer_with_size_hint(
    tmp_path, zstd_compressor, zstd_decompressor
):
    """Test that stream_writer accepts size parameter correctly."""
    src_file = tmp_path / "test.txt"
    test_content = "Stream writer test " * 200
    src_file.write_text(test_content)
    src_size = src_file.stat().st_size
    dst_file = tmp_path / "test.zst"

    with open(src_file, "rb") as src_f, open(dst_file, "wb") as dst_f:
        with zstd_compressor.stream_writer(dst_f, size=src_size) as compressor:
            compressor.write(src_f.read())

    assert dst_file.exists()
    assert dst_file.stat().st_size > 0

    decompressed_file = tmp_path / "decompressed.txt"
    with open(dst_file, "rb") as compressed_f, open(
        decompressed_file, "wb"
    ) as decompressed_f:
        zstd_decompressor.copy_stream(compressed_f, decompressed_f)

    assert decompressed_file.read_text() == test_content


def test_zstd_stream_writer_chunk_writes(tmp_path, zstd_compressor, zstd_decompressor):
    """Test that data is written to stream_writer in chunks."""
    src_file = tmp_path / "large_test.txt"
    test_content = "X" * (CHUNK_SIZE + 1000)
    src_file.write_text(test_content)
    src_size = src_file.stat().st_size
    dst_file = tmp_path / "large_test.zst"

    write_count = 0
    with open(src_file, "rb") as src_f, open(dst_file, "wb") as dst_f:
        with zstd_compressor.stream_writer(dst_f, size=src_size) as compressor:
            while data := src_f.read(CHUNK_SIZE):
                compressor.write(data)
                write_count += 1

    assert write_count >= 2
    assert dst_file.exists()

    decompressed_file = tmp_path / "decompressed.txt"
    with open(dst_file, "rb") as compressed_f, open(
        decompressed_file, "wb"
    ) as decompressed_f:
        zstd_decompressor.copy_stream(compressed_f, decompressed_f)

    assert decompressed_file.read_text() == test_content


def test_zstd_stream_writer_without_size_hint(
    tmp_path, zstd_compressor, zstd_decompressor
):
    """Test stream_writer without size parameter."""
    src_file = tmp_path / "test.txt"
    test_content = "Test without size hint " * 100
    src_file.write_text(test_content)
    dst_file = tmp_path / "test.zst"

    with open(src_file, "rb") as src_f, open(dst_file, "wb") as dst_f:
        with zstd_compressor.stream_writer(dst_f) as compressor:
            compressor.write(src_f.read())

    assert dst_file.exists()

    decompressed_file = tmp_path / "decompressed.txt"
    with open(dst_file, "rb") as compressed_f, open(
        decompressed_file, "wb"
    ) as decompressed_f:
        zstd_decompressor.copy_stream(compressed_f, decompressed_f)

    assert decompressed_file.read_text() == test_content


def test_zstd_stream_writer_empty_data(tmp_path, zstd_compressor):
    """Test stream_writer with empty data."""
    dst_file = tmp_path / "empty.zst"

    with open(dst_file, "wb") as dst_f:
        with zstd_compressor.stream_writer(dst_f) as compressor:
            compressor.write(b"")

    assert dst_file.exists()


def test_zstd_stream_writer_binary_data(tmp_path, zstd_compressor, zstd_decompressor):
    """Test stream_writer with binary data."""
    binary_data = bytes([i % 256 for i in range(10000)])
    dst_file = tmp_path / "binary.zst"

    with open(dst_file, "wb") as dst_f:
        with zstd_compressor.stream_writer(dst_f, size=len(binary_data)) as compressor:
            compressor.write(binary_data)

    assert dst_file.exists()

    decompressed_file = tmp_path / "binary_decompressed.bin"
    with open(dst_file, "rb") as compressed_f, open(
        decompressed_file, "wb"
    ) as decompressed_f:
        zstd_decompressor.copy_stream(compressed_f, decompressed_f)

    assert decompressed_file.read_bytes() == binary_data
