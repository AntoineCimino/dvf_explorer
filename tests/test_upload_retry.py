from pathlib import Path

import pytest

from src import data_host


def test_upload_retries_transient_errors(monkeypatch, tmp_path: Path):
    calls = []

    def flaky(site_url, relative, source, token):
        calls.append(relative)
        if len(calls) < 3:
            raise data_host._TransientUploadError("HTTP 502")

    monkeypatch.setattr(data_host, "_upload_once", flaky)
    monkeypatch.setattr(data_host.time, "sleep", lambda _: None)
    data_host._upload_one("https://x.test", "a.parquet", tmp_path / "a", "t")
    assert len(calls) == 3


def test_upload_gives_up_after_max_attempts(monkeypatch, tmp_path: Path):
    def always(*args):
        raise data_host._TransientUploadError("HTTP 502")

    monkeypatch.setattr(data_host, "_upload_once", always)
    monkeypatch.setattr(data_host.time, "sleep", lambda _: None)
    with pytest.raises(data_host._TransientUploadError):
        data_host._upload_one("https://x.test", "a.parquet", tmp_path / "a", "t")


def test_upload_does_not_retry_client_errors(monkeypatch, tmp_path: Path):
    calls = []

    def denied(*args):
        calls.append(1)
        raise RuntimeError("Upload failed with HTTP 403")

    monkeypatch.setattr(data_host, "_upload_once", denied)
    with pytest.raises(RuntimeError):
        data_host._upload_one("https://x.test", "a.parquet", tmp_path / "a", "t")
    assert len(calls) == 1


def test_skips_upload_when_remote_has_same_size(monkeypatch, tmp_path: Path):
    f = tmp_path / "a.parquet"
    f.write_bytes(b"12345")
    uploaded = []
    monkeypatch.setattr(data_host, "_remote_size", lambda *a: 5)
    monkeypatch.setattr(data_host, "_upload_one", lambda *a: uploaded.append(a))
    assert data_host._upload_unless_published("https://x.test", "a.parquet", f, "t") is False
    assert uploaded == []


def test_uploads_when_remote_missing_or_different(monkeypatch, tmp_path: Path):
    f = tmp_path / "a.parquet"
    f.write_bytes(b"12345")
    uploaded = []
    monkeypatch.setattr(data_host, "_upload_one", lambda *a: uploaded.append(a))
    for remote in (None, 4):
        monkeypatch.setattr(data_host, "_remote_size", lambda *a, r=remote: r)
        assert data_host._upload_unless_published("https://x.test", "a.parquet", f, "t") is True
    assert len(uploaded) == 2
