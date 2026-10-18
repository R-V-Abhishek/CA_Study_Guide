import hashlib
from io import BytesIO

import pytest

from caf_common.blob_store import BlobStore


@pytest.mark.parametrize("identifier", ["../outside", "/etc/passwd", "a" * 63, "A" * 64, "g" * 64, "a" * 64 + "\n"])
@pytest.mark.parametrize("method", ["read", "exists", "get_path"])
def test_blob_identifiers_reject_non_digests(tmp_path, identifier, method):
    store = BlobStore(tmp_path / "blobs")
    operation = {"read": store.read, "exists": store.exists, "get_path": store.get_path}[method]
    with pytest.raises(ValueError, match="SHA-256"):
        operation(identifier)


def test_valid_blob_round_trip(tmp_path):
    store = BlobStore(tmp_path / "blobs")
    digest, path = store.put(b"valid source")
    assert store.read(digest) == b"valid source"
    assert store.get_path(digest) == path
    assert store.exists(digest)
    assert store.put_stream(BytesIO(b"valid source")) == (digest, path, 12)


@pytest.mark.parametrize("operation", ["read", "put", "put_stream"])
def test_blob_symlink_directory_escape(tmp_path, operation):
    store = BlobStore(tmp_path / "blobs")
    outside = tmp_path / "outside"
    outside.mkdir()
    payload = b"source"
    digest = hashlib.sha256(payload).hexdigest()
    (store.base_dir / digest[:2]).symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="outside"):
        if operation == "read":
            store.read(digest)
        elif operation == "put":
            store.put(payload)
        else:
            store.put_stream(BytesIO(payload))
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("suffix", [".pdf", ".tmp"])
def test_blob_symlink_file_escape(tmp_path, suffix):
    store = BlobStore(tmp_path / "blobs")
    payload = b"source"
    digest = hashlib.sha256(payload).hexdigest()
    destination = store.base_dir / digest[:2] / digest[2:4]
    destination.mkdir(parents=True)
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"preserve")
    (destination / (digest + suffix)).symlink_to(outside)
    with pytest.raises(ValueError, match="outside"):
        store.put(payload)
    assert outside.read_bytes() == b"preserve"


def test_stream_temp_directory_cannot_escape(tmp_path):
    store = BlobStore(tmp_path / "blobs")
    outside = tmp_path / "outside"
    outside.mkdir()
    (store.base_dir / "tmp").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="outside"):
        store.put_stream(BytesIO(b"source"))
    assert list(outside.iterdir()) == []
