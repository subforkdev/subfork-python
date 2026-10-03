"""File transfer contracts, authorization boundaries and failed-download cleanup."""

from pathlib import Path
from typing import Iterator

import httpx
import pytest

from subfork import APIError, Subfork
from subfork.errors import InvalidResponseError, TransportError


def test_upload_returns_artifact_and_streams_multipart(tmp_path: Path) -> None:
    """Uploads return server metadata and use the existing upload field."""
    source = tmp_path / "source.txt"
    source.write_text("Source document")

    def handle(request: httpx.Request) -> httpx.Response:
        """Inspect the upload and the asset-list query."""
        assert request.headers["authorization"] == "Bearer test-key"
        if request.method == "GET":
            assert request.url.params["include_generated"] == "true"
            return httpx.Response(200, json={"assets": []})
        assert request.url.path == "/api/v1/graphs/g_test/assets/files"
        assert b'name="upload"; filename="source.txt"' in request.content
        assert b"Source document" in request.content
        return httpx.Response(201, json={"artifact_id": "art_test", "size_bytes": 15})

    with Subfork("test-key", transport=httpx.MockTransport(handle)) as client:
        assert client.assets.upload("g_test", source)["artifact_id"] == "art_test"
        assert client.assets.list("g_test", include_generated=True) == {"assets": []}


@pytest.mark.parametrize("redirect", [False, True])
def test_download_and_overwrite(tmp_path: Path, redirect: bool) -> None:
    """Stream bytes and never send the API key or cookies to storage."""
    seen = []

    def handle(request: httpx.Request) -> httpx.Response:
        """Serve a local artifact or a signed storage redirect."""
        seen.append(request)
        if request.url.host == "storage.example.com":
            assert "authorization" not in request.headers
            assert "cookie" not in request.headers
            return httpx.Response(200, content=b"MP3 bytes")
        assert request.headers["authorization"] == "Bearer test-key"
        if redirect:
            return httpx.Response(
                302, headers={"location": "https://storage.example.com/audio?signature=test"}
            )
        return httpx.Response(200, content=b"MP3 bytes")

    path = tmp_path / "audio.mp3"
    with Subfork("test-key", transport=httpx.MockTransport(handle)) as client:
        assert client.artifacts.download("art_test", path) == path
        assert path.read_bytes() == b"MP3 bytes"
        count = len(seen)
        with pytest.raises(FileExistsError):
            client.artifacts.download("art_test", path)
        assert len(seen) == count
        client.artifacts.download("art_test", path, overwrite=True)
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("mode", ["oversize", "http", "insecure", "credentials", "redirect-loop"])
def test_failed_download_preserves_destination(tmp_path: Path, mode: str) -> None:
    """Reject failed, oversized or unsafe transfers without destroying old files."""

    def handle(request: httpx.Request) -> httpx.Response:
        """Return the chosen transfer failure."""
        if mode == "http":
            return httpx.Response(409, json={"detail": "private provider data"})
        if mode in {"insecure", "credentials", "redirect-loop"}:
            target = {
                "insecure": "http://storage.example.com/file",
                "credentials": "https://user:pass@storage.example.com/file",
                "redirect-loop": "https://storage.example.com/file",
            }[mode]
            return httpx.Response(302, headers={"location": target})
        return httpx.Response(200, content=b"too many bytes")

    path = tmp_path / "audio.mp3"
    path.write_bytes(b"original")
    with Subfork("test-key", transport=httpx.MockTransport(handle)) as client:
        with pytest.raises((ValueError, APIError, InvalidResponseError)):
            client.artifacts.download("art_test", path, overwrite=True, max_bytes=3)
    assert path.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [path]


def test_interrupted_download_removes_partial_file(tmp_path: Path) -> None:
    """A transport failure cannot replace an existing destination."""

    class BrokenStream(httpx.SyncByteStream):
        """Yield some bytes and then simulate a lost connection."""

        def __iter__(self) -> Iterator[bytes]:
            """Stream a chunk before failing."""
            yield b"partial" * 20000
            raise httpx.ReadError("sensitive-url-must-not-be-reflected")

    def handle(request: httpx.Request) -> httpx.Response:
        """Return a stream that fails after writing begins."""
        return httpx.Response(200, stream=BrokenStream())

    path = tmp_path / "output.mp4"
    path.write_bytes(b"original")
    with Subfork("test-key", transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(TransportError, match="Artifact download could not be completed"):
            client.artifacts.download("art_test", path, overwrite=True)
    assert path.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [path]
