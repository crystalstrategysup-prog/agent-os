"""Exercise the public archive lifecycle with a disposable indexed library."""

import pytest

from agent_os.handoff import Library
from agent_os.handoff_cli import command
from agent_os.handoff_pack import PACK_HEADER, POINTER
from agent_os.handoff_store import HandoffError
from test_indexed_handoff import P, TOPICS, accept, object_path


@pytest.fixture
def old_page(tmp_path):
    library = Library.create(tmp_path / "library", P, topics=TOPICS)
    accept(library, 1)
    accept(library, 2)
    library.grant_access("reader:temporary", P)
    query = {"limit": 1}
    cursor = library.search(query, P)["next_cursor"]
    guest = library.search(query, "reader:temporary")["next_cursor"]
    expected = library.search(query, P, cursor=cursor)
    _, _, routes, _ = library._view(P)
    page = object_path(library, routes["current"]["handoff_id"])
    selection = tmp_path / "pages.txt"
    selection.write_text(page.name + "\n")
    library.revoke_access("reader:temporary", P)
    accept(library, 3)
    return library, query, cursor, guest, expected, page, selection


def build(library, selection, destination, *, budget="1048576"):
    return command([
        "--root", str(library.path), "pack-build",
        "--selection", str(selection), "--directory", str(destination),
        "--max-bytes", budget, "--reserve-bytes", "0",
    ])


def attach(library, destination, digest):
    return command([
        "--root", str(library.path), "pack-attach",
        "--directory", str(destination), "--manifest-sha256", digest,
    ])


def unpack(library, reserve="0"):
    return command(["--root", str(library.path), "pack-restore", "--reserve-bytes", reserve])


def test_pack_cli_historical_cursor_acl_and_retryable_restore(old_page, tmp_path):
    library, query, cursor, guest, expected, page, selection = old_page
    archive = tmp_path / "archive"
    contents = page.read_bytes()
    digest = build(library, selection, archive)["manifest_sha256"]
    assert page.read_bytes() == contents

    with pytest.raises(HandoffError, match="INVALID_PACK"):
        attach(library, archive, "f" * 64)
    assert not (library.path / POINTER).exists()
    assert attach(library, archive, digest)["status"] == "attached"

    page.unlink()  # Only the disposable fixture's exact archived object.
    result = Library(library.path).search(query, P, cursor=cursor)
    assert result["results"] == expected["results"]
    assert result["generation"] == expected["generation"]
    assert len(Library(library.path).search({**query, "limit": 10}, P)["results"]) == 3

    with pytest.raises(HandoffError, match="NOT_AUTHORIZED_OR_NOT_FOUND"):
        Library(library.path).search(query, "reader:temporary", cursor=guest)
    with pytest.raises(HandoffError, match="NOT_AUTHORIZED_OR_NOT_FOUND"):
        library.restore_index_pack("reader:temporary", reserve=0)
    with pytest.raises(HandoffError, match="PACK_CAPACITY"):
        unpack(library, reserve=str(1 << 90))
    assert (library.path / POINTER).is_file()
    assert not page.exists()

    assert unpack(library)["status"] == "restored"
    assert page.read_bytes() == contents
    assert (archive / "MANIFEST.json").is_file()
    assert not (library.path / POINTER).exists()
    assert Library(library.path).search(query, P, cursor=cursor)["results"] == expected["results"]


def test_build_rejects_bad_selection_and_capacity_without_leaving_archive(old_page, tmp_path):
    library, _, _, _, _, page, selection = old_page
    archive = tmp_path / "archive"
    with pytest.raises(HandoffError, match="PACK_CAPACITY"):
        build(library, selection, archive, budget="4096")
    assert not archive.exists()
    selection.write_text((page.name + "\n") * 2)
    with pytest.raises(HandoffError, match="INVALID_PACK_SELECTION"):
        build(library, selection, archive)
    assert not archive.exists() and page.is_file()


def test_corrupt_loose_file_is_not_hidden_by_pack_and_corrupt_pack_is_refused(old_page, tmp_path):
    library, query, cursor, _, _, page, selection = old_page
    archive = tmp_path / "archive"
    digest = build(library, selection, archive)["manifest_sha256"]
    attach(library, archive, digest)
    page.write_bytes(b"corrupt")
    with pytest.raises(HandoffError, match="INTEGRITY_FAILED"):
        Library(library.path).search(query, P, cursor=cursor)
    page.unlink()
    with (archive / "pack.bin").open("r+b") as stream:
        stream.seek(len(PACK_HEADER))
        byte = stream.read(1)
        stream.seek(len(PACK_HEADER))
        stream.write(bytes([byte[0] ^ 1]))
    with pytest.raises(HandoffError, match="INVALID_PACK"):
        Library(library.path).search(query, P, cursor=cursor)
    with pytest.raises(HandoffError, match="INVALID_PACK"):
        unpack(library)
    assert not page.exists()
    assert (library.path / POINTER).is_file()


def test_reader_survives_detachment_between_its_loose_and_archive_reads(old_page, tmp_path, monkeypatch):
    from agent_os import handoff_pack

    library, query, cursor, _, expected, page, selection = old_page
    archive = tmp_path / "archive"
    digest = build(library, selection, archive)["manifest_sha256"]
    attach(library, archive, digest)
    page.unlink()
    read_packed = handoff_pack.read_packed

    def completed_rollback(store, digest, size):
        assert unpack(library)["status"] == "restored"
        return read_packed(store, digest, size)

    monkeypatch.setattr(handoff_pack, "read_packed", completed_rollback)
    assert Library(library.path).search(query, P, cursor=cursor)["results"] == expected["results"]
