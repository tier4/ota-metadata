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
import json
import base64
import tempfile
import pytest

import metadata_sign
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import ec


class TestCryptographyFunctions:
    """Test class for cryptography-related functions in metadata_sign module."""

    def setup_method(self):
        """Set up test fixtures."""
        # Generate a test private key for testing
        self.private_key = ec.generate_private_key(ec.SECP256R1())
        self.private_key_pem = self.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        # Create test data
        self.test_data = "test data for signing"
        self.test_file_content = "test file content"
        self.test_json_data = {"test": "data", "number": 123}

    def test_urlsafe_b64encode_with_string(self):
        """Test urlsafe_b64encode with string input."""
        test_string = "Hello, World!"
        result = metadata_sign.urlsafe_b64encode(test_string)

        # Decode and verify
        decoded = base64.urlsafe_b64decode(result.encode())
        assert decoded.decode() == test_string
        assert isinstance(result, str)

    def test_urlsafe_b64encode_with_bytes(self):
        """Test urlsafe_b64encode with bytes input."""
        test_bytes = b"Hello, World!"
        result = metadata_sign.urlsafe_b64encode(test_bytes)

        # Decode and verify
        decoded = base64.urlsafe_b64decode(result.encode())
        assert decoded == test_bytes
        assert isinstance(result, str)

    def test_urlsafe_b64encode_with_json(self):
        """Test urlsafe_b64encode with JSON data."""
        json_string = json.dumps(self.test_json_data)
        result = metadata_sign.urlsafe_b64encode(json_string)

        # Decode and verify
        decoded = base64.urlsafe_b64decode(result.encode())
        decoded_json = json.loads(decoded.decode())
        assert decoded_json == self.test_json_data

    def test_gen_header(self):
        """Test gen_header function."""
        header = metadata_sign.gen_header()

        # Decode and verify header structure
        decoded_header = base64.urlsafe_b64decode(header.encode())
        header_data = json.loads(decoded_header.decode())

        assert header_data == {"alg": "ES256"}
        assert isinstance(header, str)

    def test_file_sha256(self):
        """Test _file_sha256 function."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as temp_file:
            temp_file.write(self.test_file_content)
            temp_file_path = temp_file.name

        try:
            # Calculate expected hash
            import hashlib

            expected_hash = hashlib.sha256(self.test_file_content.encode()).hexdigest()

            # Test the function
            result_hash = metadata_sign._file_sha256(temp_file_path)
            assert result_hash == expected_hash
        finally:
            os.unlink(temp_file_path)

    def test_file_sha256_with_binary_content(self):
        """Test _file_sha256 function with binary content."""
        binary_content = b"\x00\x01\x02\x03\x04\x05"

        with tempfile.NamedTemporaryFile(mode="wb", delete=False) as temp_file:
            temp_file.write(binary_content)
            temp_file_path = temp_file.name

        try:
            # Calculate expected hash
            import hashlib

            expected_hash = hashlib.sha256(binary_content).hexdigest()

            # Test the function
            result_hash = metadata_sign._file_sha256(temp_file_path)
            assert result_hash == expected_hash
        finally:
            os.unlink(temp_file_path)

    def test_sign_function(self):
        """Test sign function with cryptography."""
        with tempfile.NamedTemporaryFile(mode="wb", delete=False) as key_file:
            key_file.write(self.private_key_pem)
            key_file_path = key_file.name

        try:
            # Test signing
            signature = metadata_sign.sign(key_file_path, self.test_data)

            # Verify signature format
            assert isinstance(signature, str)

            # Decode signature
            signature_bytes = base64.urlsafe_b64decode(signature.encode())

            # Verify signature using public key
            public_key = self.private_key.public_key()
            try:
                public_key.verify(
                    signature_bytes, self.test_data.encode(), ec.ECDSA(hashes.SHA256())
                )
                # If no exception is raised, signature is valid
                assert True
            except Exception:
                pytest.fail("Signature verification failed")
        finally:
            os.unlink(key_file_path)

    def test_sign_function_with_invalid_key_file(self):
        """Test sign function with invalid key file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as invalid_key_file:
            invalid_key_file.write("invalid key content")
            invalid_key_file_path = invalid_key_file.name

        try:
            with pytest.raises(ValueError):
                metadata_sign.sign(invalid_key_file_path, self.test_data)
        finally:
            os.unlink(invalid_key_file_path)

    def test_sign_function_with_nonexistent_file(self):
        """Test sign function with non-existent key file."""
        with pytest.raises(FileNotFoundError):
            metadata_sign.sign("/nonexistent/key/file.pem", self.test_data)

    def test_gen_payload(self):
        """Test gen_payload function."""
        # Create temporary files for testing
        temp_files = {}
        file_contents = {
            "directory": "dir content",
            "symlink": "symlink content",
            "regular": "regular content",
            "persistent": "persistent content",
            "certificate": "cert content",
            "total_regular_size": "1024",
        }

        try:
            # Create temporary files
            for file_type, content in file_contents.items():
                temp_file = tempfile.NamedTemporaryFile(mode="w", delete=False)
                temp_file.write(content)
                temp_file.close()
                temp_files[file_type] = temp_file.name

            # Test gen_payload
            payload = metadata_sign.gen_payload(
                directory_file=temp_files["directory"],
                symlink_file=temp_files["symlink"],
                regular_file=temp_files["regular"],
                persistent_file=temp_files["persistent"],
                rootfs_directory="test_rootfs",
                certificate_file=temp_files["certificate"],
                total_regular_size_file=temp_files["total_regular_size"],
                compressed_rootfs_directory="compressed_test_rootfs",
            )

            # Decode and verify payload
            decoded_payload = base64.urlsafe_b64decode(payload.encode())
            payload_data = json.loads(decoded_payload.decode())

            assert isinstance(payload_data, list)
            assert len(payload_data) >= 7  # Basic required fields

            # Check version
            assert payload_data[0] == {"version": 1}

            # Check specific file entries (directory, symlink, regular, persistent, certificate)
            # These have both name and hash
            file_entries = [
                payload_data[1],
                payload_data[2],
                payload_data[3],
                payload_data[4],
                payload_data[6],
            ]
            for entry in file_entries:
                assert "hash" in entry
                hash_value = list(entry.values())[1]  # hash is the second value
                assert len(hash_value) == 64  # SHA256 hex length

            # Check rootfs directory (doesn't have hash)
            assert payload_data[5] == {"rootfs_directory": "test_rootfs"}

            # Check optional fields are present
            total_size_found = any(
                "total_regular_size" in item for item in payload_data
            )
            compressed_found = any(
                "compressed_rootfs_directory" in item for item in payload_data
            )
            assert total_size_found
            assert compressed_found

        finally:
            # Clean up temporary files
            for temp_file_path in temp_files.values():
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)

    def test_gen_payload_without_optional_files(self):
        """Test gen_payload function without optional files."""
        # Create temporary files for required parameters only
        temp_files = {}
        file_contents = {
            "directory": "dir content",
            "symlink": "symlink content",
            "regular": "regular content",
            "persistent": "persistent content",
            "certificate": "cert content",
        }

        try:
            # Create temporary files
            for file_type, content in file_contents.items():
                temp_file = tempfile.NamedTemporaryFile(mode="w", delete=False)
                temp_file.write(content)
                temp_file.close()
                temp_files[file_type] = temp_file.name

            # Test gen_payload without optional parameters
            payload = metadata_sign.gen_payload(
                directory_file=temp_files["directory"],
                symlink_file=temp_files["symlink"],
                regular_file=temp_files["regular"],
                persistent_file=temp_files["persistent"],
                rootfs_directory="test_rootfs",
                certificate_file=temp_files["certificate"],
                total_regular_size_file="/nonexistent/file",  # Should not exist
                compressed_rootfs_directory=None,
            )

            # Decode and verify payload
            decoded_payload = base64.urlsafe_b64decode(payload.encode())
            payload_data = json.loads(decoded_payload.decode())

            assert isinstance(payload_data, list)
            assert len(payload_data) == 7  # Only required fields

        finally:
            # Clean up temporary files
            for temp_file_path in temp_files.values():
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)

    def test_sign_metadata_integration(self):
        """Test the complete sign_metadata function integration."""
        # Create temporary files for all required parameters
        temp_files = {}
        file_contents = {
            "directory": "dir content",
            "symlink": "symlink content",
            "regular": "regular content",
            "persistent": "persistent content",
            "certificate": "cert content",
            "total_regular_size": "1024",
        }

        try:
            # Create temporary files
            for file_type, content in file_contents.items():
                temp_file = tempfile.NamedTemporaryFile(mode="w", delete=False)
                temp_file.write(content)
                temp_file.close()
                temp_files[file_type] = temp_file.name

            # Create private key file
            key_file = tempfile.NamedTemporaryFile(mode="wb", delete=False)
            key_file.write(self.private_key_pem)
            key_file.close()
            temp_files["key"] = key_file.name

            # Create output file
            output_file = tempfile.NamedTemporaryFile(delete=False)
            output_file.close()
            temp_files["output"] = output_file.name

            # Test sign_metadata
            metadata_sign.sign_metadata(
                directory_file=temp_files["directory"],
                symlink_file=temp_files["symlink"],
                regular_file=temp_files["regular"],
                persistent_file=temp_files["persistent"],
                rootfs_directory="test_rootfs",
                sign_key_file=temp_files["key"],
                cert_file=temp_files["certificate"],
                total_regular_size_file=temp_files["total_regular_size"],
                compressed_rootfs_directory="compressed_test_rootfs",
                output_file=temp_files["output"],
            )

            # Verify output file exists and has content
            assert os.path.exists(temp_files["output"])

            with open(temp_files["output"], "r") as f:
                jwt_content = f.read()

            # Verify JWT structure (header.payload.signature)
            parts = jwt_content.split(".")
            assert len(parts) == 3

            # Verify each part is valid base64
            for part in parts:
                try:
                    base64.urlsafe_b64decode(part + "==")  # Add padding if needed
                except Exception:
                    pytest.fail(f"Invalid base64 in JWT part: {part}")

            # Verify header
            header_data = json.loads(base64.urlsafe_b64decode(parts[0] + "==").decode())
            assert header_data == {"alg": "ES256"}

            # Verify payload structure
            payload_data = json.loads(
                base64.urlsafe_b64decode(parts[1] + "==").decode()
            )
            assert isinstance(payload_data, list)
            assert payload_data[0] == {"version": 1}

        finally:
            # Clean up temporary files
            for temp_file_path in temp_files.values():
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)

    def test_cryptography_key_formats(self):
        """Test different cryptography key formats and algorithms."""
        # Test with different curve
        for curve in [ec.SECP256R1(), ec.SECP384R1()]:
            private_key = ec.generate_private_key(curve)
            private_key_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )

            with tempfile.NamedTemporaryFile(mode="wb", delete=False) as key_file:
                key_file.write(private_key_pem)
                key_file_path = key_file.name

            try:
                # Should work with SECP256R1 but may fail with other curves
                # depending on the implementation
                if curve.name == "secp256r1":
                    signature = metadata_sign.sign(key_file_path, self.test_data)
                    assert isinstance(signature, str)

                    # Verify signature
                    signature_bytes = base64.urlsafe_b64decode(signature.encode())
                    public_key = private_key.public_key()
                    try:
                        public_key.verify(
                            signature_bytes,
                            self.test_data.encode(),
                            ec.ECDSA(hashes.SHA256()),
                        )
                        assert True
                    except Exception:
                        pytest.fail("Signature verification failed")
            finally:
                os.unlink(key_file_path)

    def test_edge_cases_and_error_handling(self):
        """Test edge cases and error handling in cryptography functions."""

        # Test empty data signing
        with tempfile.NamedTemporaryFile(mode="wb", delete=False) as key_file:
            key_file.write(self.private_key_pem)
            key_file_path = key_file.name

        try:
            empty_signature = metadata_sign.sign(key_file_path, "")
            assert isinstance(empty_signature, str)
        finally:
            os.unlink(key_file_path)

        # Test very long data signing
        long_data = "x" * 10000
        with tempfile.NamedTemporaryFile(mode="wb", delete=False) as key_file:
            key_file.write(self.private_key_pem)
            key_file_path = key_file.name

        try:
            long_signature = metadata_sign.sign(key_file_path, long_data)
            assert isinstance(long_signature, str)
        finally:
            os.unlink(key_file_path)

        # Test unicode data encoding
        unicode_data = "こんにちは世界🌍"
        encoded_result = metadata_sign.urlsafe_b64encode(unicode_data)
        decoded = base64.urlsafe_b64decode(encoded_result.encode()).decode()
        assert decoded == unicode_data

    def test_performance_and_consistency(self):
        """Test performance and consistency of cryptographic operations."""
        # Test that the same input produces the same hash
        test_content = "consistent test content"

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as temp_file:
            temp_file.write(test_content)
            temp_file_path = temp_file.name

        try:
            hash1 = metadata_sign._file_sha256(temp_file_path)
            hash2 = metadata_sign._file_sha256(temp_file_path)
            assert hash1 == hash2
        finally:
            os.unlink(temp_file_path)

        # Test that header generation is consistent
        header1 = metadata_sign.gen_header()
        header2 = metadata_sign.gen_header()
        assert header1 == header2

        # Test that different signatures of the same data are different
        # (due to randomness in ECDSA)
        with tempfile.NamedTemporaryFile(mode="wb", delete=False) as key_file:
            key_file.write(self.private_key_pem)
            key_file_path = key_file.name

        try:
            sig1 = metadata_sign.sign(key_file_path, self.test_data)
            sig2 = metadata_sign.sign(key_file_path, self.test_data)
            # ECDSA signatures should be different due to randomness
            assert sig1 != sig2
        finally:
            os.unlink(key_file_path)
