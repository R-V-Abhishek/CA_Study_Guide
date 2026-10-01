"""Fail closed on normal, administrative, and alternate database connections."""

import socket
import psycopg
import pytest
import sqlalchemy as sa
from pathlib import Path
from caf_common.backup import create_backup, verify_backup
from caf_common.blob_store import BlobStore
from caf_common.db_safety import assert_safe_database
from caf_common.settings import Settings
from caf_common.settings import get_settings
from caf_l1.discover import LinkDiscoverer
from caf_l1.fetcher import DocumentFetcher
from caf_l1.robots import PolitenessManager
from caf_l3.llm import GeminiClassifier


@pytest.mark.parametrize("url", [
    "postgresql+psycopg://postgres:secret@127.0.0.1:5432/caf",
    "postgresql+psycopg://postgres:secret@127.0.0.1:5432/postgres",
    "postgresql+psycopg://postgres:secret@127.0.0.1:5433/caf_verify",
])
def test_normal_targets_rejected(url, monkeypatch):
    with pytest.raises(RuntimeError, match="allowlist"):
        assert_safe_database(url)
    monkeypatch.setenv("DATABASE_URL", url)
    with pytest.raises(RuntimeError, match="allowlist"):
        Settings.load()
    with pytest.raises(RuntimeError, match="allowlist"):
        with sa.create_engine(url).connect():
            pytest.fail("Unsafe connection opened")


def test_direct_admin_connection_rejected():
    with pytest.raises(RuntimeError, match="allowlist"):
        psycopg.connect(host="127.0.0.1", port=5432, dbname="postgres")


def test_external_acquisition_disabled():
    with socket.socket() as sock:
        with pytest.raises(RuntimeError, match="disabled"):
            sock.connect(("8.8.8.8", 443))


def test_application_storage_and_backup_targets_rejected():
    with pytest.raises(RuntimeError, match="storage target rejected"):
        BlobStore(Path("data/blobs"))
    with pytest.raises(RuntimeError, match="storage target rejected"):
        create_backup(backup_dir=Path("data/backups"))
    with pytest.raises(RuntimeError, match="storage target rejected"):
        verify_backup(dump_file=Path("data/backups/caf_real.dump"))


def test_acquisition_and_models_disabled_before_external_calls(session):
    politeness = PolitenessManager("isolated-tests")
    discoverer = LinkDiscoverer([], politeness)
    fetcher = DocumentFetcher(BlobStore(get_settings().storage.blob_dir), politeness)
    with pytest.raises(RuntimeError, match="acquisition disabled"):
        discoverer.discover_source({"id": "blocked", "url": "https://icai.org"}, session)
    with pytest.raises(RuntimeError, match="acquisition disabled"):
        fetcher.fetch_pending(session)
    with pytest.raises(RuntimeError, match="acquisition disabled"):
        politeness.is_allowed("https://icai.org")
    assert not GeminiClassifier(session).is_available()
