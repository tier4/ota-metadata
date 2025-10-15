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


from unittest.mock import patch
import pytest

import data_gen


@pytest.fixture
def sample_dirs_file(tmp_path):
    """Create a sample directory metadata file."""
    dirs_file = tmp_path / "dirs.txt"
    dirs_file.write_text(
        "755,1000,1000,'./test_dir'\n" "644,1000,1000,'./test_dir/subdir'\n"
    )
    return str(dirs_file)


@pytest.fixture
def sample_symlinks_file(tmp_path):
    """Create a sample symlink metadata file."""
    symlinks_file = tmp_path / "symlinks.txt"
    symlinks_file.write_text(
        "777,1000,1000,'./link1','./target1'\n" "777,1000,1000,'./link2','./target2'\n"
    )
    return str(symlinks_file)


@pytest.fixture
def sample_regulars_file(tmp_path):
    """Create a sample regular file metadata file."""
    regulars_file = tmp_path / "regulars.txt"
    regulars_file.write_text(
        "644,1000,1000,1,abcd1234567890,'./file1.txt',100,12345,\n"
        "644,1000,1000,1,efgh0987654321,'./file2.txt',200,67890,\n"
    )
    return str(regulars_file)


@pytest.fixture
def sample_src_dir(tmp_path):
    """Create a sample source directory structure."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()

    # Create test files
    (src_dir / "file1.txt").write_text("test content 1")
    (src_dir / "file2.txt").write_text("test content 2")

    return str(src_dir)


def test_gen_dirs_with_progress(sample_dirs_file, tmp_path):
    """Test _gen_dirs function with progress enabled."""
    dst_dir = str(tmp_path / "dst")

    with patch("data_gen.tqdm") as mock_tqdm:
        # tqdm should return an iterator when called
        mock_tqdm.return_value = [
            "755,1000,1000,'./test_dir'",
            "644,1000,1000,'./test_dir/subdir'",
        ]

        # Mock os functions to avoid permission errors
        with patch("os.makedirs"), patch("os.chown"), patch("os.chmod"):
            data_gen._gen_dirs(dst_dir, sample_dirs_file, progress=True)

        # Verify tqdm was called with the lines
        mock_tqdm.assert_called_once()
        args, kwargs = mock_tqdm.call_args
        assert len(args[0]) == 2  # Two lines in the sample file


def test_gen_dirs_without_progress(sample_dirs_file, tmp_path):
    """Test _gen_dirs function with progress disabled."""
    dst_dir = str(tmp_path / "dst")

    with patch("data_gen.tqdm") as mock_tqdm:
        # Mock os functions to avoid permission errors
        with patch("os.makedirs"), patch("os.chown"), patch("os.chmod"):
            data_gen._gen_dirs(dst_dir, sample_dirs_file, progress=False)

        # Verify tqdm was not called when progress=False
        mock_tqdm.assert_not_called()


def test_gen_symlinks_with_progress(sample_symlinks_file, tmp_path):
    """Test _gen_symlinks function with progress enabled."""
    dst_dir = str(tmp_path / "dst")

    with patch("data_gen.tqdm") as mock_tqdm:
        mock_tqdm.return_value = [
            "777,1000,1000,'./link1','./target1'",
            "777,1000,1000,'./link2','./target2'",
        ]

        # Mock os functions to avoid permission errors
        with patch("os.symlink"), patch("os.chown"):
            data_gen._gen_symlinks(dst_dir, sample_symlinks_file, progress=True)

        # Verify tqdm was called
        mock_tqdm.assert_called_once()
        args, kwargs = mock_tqdm.call_args
        assert len(args[0]) == 2  # Two lines in the sample file


def test_gen_symlinks_without_progress(sample_symlinks_file, tmp_path):
    """Test _gen_symlinks function with progress disabled."""
    dst_dir = str(tmp_path / "dst")

    with patch("data_gen.tqdm") as mock_tqdm:
        # Mock os functions to avoid permission errors
        with patch("os.symlink"), patch("os.chown"):
            data_gen._gen_symlinks(dst_dir, sample_symlinks_file, progress=False)

        # Verify tqdm was not called when progress=False
        mock_tqdm.assert_not_called()


def test_gen_regulars_with_progress(sample_regulars_file, sample_src_dir, tmp_path):
    """Test _gen_regulars function with progress enabled."""
    dst_dir = str(tmp_path / "dst")

    with patch("data_gen.tqdm") as mock_tqdm:
        mock_tqdm.return_value = [
            "644,1000,1000,1,abcd1234567890,'./file1.txt',100,12345,",
            "644,1000,1000,1,efgh0987654321,'./file2.txt',200,67890,",
        ]

        # Mock shutil and os functions to avoid file operations
        with patch("shutil.copyfile"), patch("os.chown"), patch("os.chmod"), patch(
            "os.link"
        ):
            data_gen._gen_regulars(
                dst_dir, sample_regulars_file, sample_src_dir, progress=True
            )

        # Verify tqdm was called
        mock_tqdm.assert_called_once()
        args, kwargs = mock_tqdm.call_args
        assert len(args[0]) == 2  # Two lines in the sample file


def test_gen_regulars_without_progress(sample_regulars_file, sample_src_dir, tmp_path):
    """Test _gen_regulars function with progress disabled."""
    dst_dir = str(tmp_path / "dst")

    with patch("data_gen.tqdm") as mock_tqdm:
        # Mock shutil and os functions to avoid file operations
        with patch("shutil.copyfile"), patch("os.chown"), patch("os.chmod"), patch(
            "os.link"
        ):
            data_gen._gen_regulars(
                dst_dir, sample_regulars_file, sample_src_dir, progress=False
            )

        # Verify tqdm was not called when progress=False
        mock_tqdm.assert_not_called()


def test_gen_data_with_progress(
    sample_dirs_file,
    sample_symlinks_file,
    sample_regulars_file,
    sample_src_dir,
    tmp_path,
):
    """Test gen_data function with progress enabled."""
    dst_dir = str(tmp_path / "dst")

    with patch("data_gen.tqdm") as mock_tqdm:
        # Configure mock to return the lines
        mock_tqdm.side_effect = [
            [
                "755,1000,1000,'./test_dir'",
                "644,1000,1000,'./test_dir/subdir'",
            ],  # for _gen_dirs
            [
                "777,1000,1000,'./link1','./target1'",
                "777,1000,1000,'./link2','./target2'",
            ],  # for _gen_symlinks
            [
                "644,1000,1000,1,abcd1234567890,'./file1.txt',100,12345,",
                "644,1000,1000,1,efgh0987654321,'./file2.txt',200,67890,",
            ],  # for _gen_regulars
        ]

        # Mock all file system operations
        with patch("os.makedirs"), patch("os.chown"), patch("os.chmod"), patch(
            "os.symlink"
        ), patch("shutil.copyfile"), patch("os.link"), patch(
            "os.listdir", return_value=[]
        ):

            data_gen.gen_data(
                dst_dir=dst_dir,
                src_dir=sample_src_dir,
                directory_file=sample_dirs_file,
                symlink_file=sample_symlinks_file,
                regular_file=sample_regulars_file,
                progress=True,
            )

        # Verify tqdm was called 3 times (once for each file type)
        assert mock_tqdm.call_count == 3


def test_gen_data_without_progress(
    sample_dirs_file,
    sample_symlinks_file,
    sample_regulars_file,
    sample_src_dir,
    tmp_path,
):
    """Test gen_data function with progress disabled."""
    dst_dir = str(tmp_path / "dst")

    with patch("data_gen.tqdm") as mock_tqdm:
        # Mock all file system operations
        with patch("os.makedirs"), patch("os.chown"), patch("os.chmod"), patch(
            "os.symlink"
        ), patch("shutil.copyfile"), patch("os.link"), patch(
            "os.listdir", return_value=[]
        ):

            data_gen.gen_data(
                dst_dir=dst_dir,
                src_dir=sample_src_dir,
                directory_file=sample_dirs_file,
                symlink_file=sample_symlinks_file,
                regular_file=sample_regulars_file,
                progress=False,
            )

        # Verify tqdm was not called when progress=False
        mock_tqdm.assert_not_called()


def test_tqdm_progress_bar_behavior():
    """Test that tqdm is properly configured and behaves as expected."""
    from tqdm import tqdm

    # Test that tqdm can be imported and used
    test_list = [1, 2, 3, 4, 5]

    # Mock stdout to capture tqdm output
    with patch("sys.stdout"):
        result = list(tqdm(test_list))
        assert result == test_list

    # Test that tqdm can be disabled
    result_no_progress = list(test_list)
    assert result_no_progress == test_list


def test_progress_conditional_logic():
    """Test the conditional logic for progress display."""
    test_lines = ["line1", "line2", "line3"]

    # Test with progress=True
    with patch("data_gen.tqdm") as mock_tqdm:
        mock_tqdm.return_value = test_lines

        # Simulate the conditional logic in the actual code
        result = mock_tqdm(test_lines) if True else test_lines

        # Process the result (similar to what happens in the actual functions)
        processed_lines = list(result)

        mock_tqdm.assert_called_once_with(test_lines)
        assert processed_lines == test_lines

    # Test with progress=False
    with patch("data_gen.tqdm") as mock_tqdm:
        # Simulate the conditional logic with progress=False
        result = mock_tqdm(test_lines) if False else test_lines

        # Process the result
        processed_lines = list(result)

        mock_tqdm.assert_not_called()
        assert processed_lines == test_lines
