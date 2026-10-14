import pytest

from app.paths import NotFound, PathError, parse_virtual, resolve, validate_name

BAD_NAMES = [
    "", ".", "..", "a/b", "a\\b", "a\x00b", "x" * 101, "trail.", "trail ", "con", "NUL.txt", "Com1", "lpt9.log",
    "a‮b", "a​b", "a﻿b", "a b", "tab\tname", "new\nline", "a:b", "a*b", 'a"b', "a<b", "a|b", "a?b",
    "\ud800", "\U000f0000",
]


@pytest.mark.parametrize("name", BAD_NAMES)
def test_bad_names_are_rejected(name):
    with pytest.raises(PathError):
        validate_name(name)


def test_names_are_nfc_normalised_and_unicode_is_allowed():
    assert validate_name("é") == "é"
    assert validate_name("Báo cáo 2025.txt") == "Báo cáo 2025.txt"
    assert validate_name("x" * 100) == "x" * 100


def test_non_string_name_is_rejected():
    with pytest.raises(PathError):
        validate_name(5)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "raw",
    ["a", "", "../x", "/..", "/a/../b", "/a//b", "/./a", "//", "/a/b/c/d/e/f/g", "/a\x00", "/" + "x" * 800],
)
def test_bad_virtual_paths(raw):
    with pytest.raises(PathError):
        parse_virtual(raw)


def test_virtual_path_parsing():
    assert parse_virtual("/") == []
    assert parse_virtual("/a/b/") == ["a", "b"]
    assert parse_virtual("/a/b/c/d/e/f") == ["a", "b", "c", "d", "e", "f"]
    assert parse_virtual("/%2e%2e") == ["%2e%2e"]  # a literal name, not a dot segment
    with pytest.raises(PathError):
        parse_virtual(5)  # type: ignore[arg-type]


def test_resolve_stays_inside_and_reports_missing(tmp_path):
    root = tmp_path / "root"
    (root / "d").mkdir(parents=True)
    (root / "d" / "f.txt").write_text("x")
    assert resolve(root, "/d/f.txt").virtual == "/d/f.txt"
    assert resolve(root, "/").parts == ()
    with pytest.raises(NotFound):
        resolve(root, "/d/missing")
    with pytest.raises(NotFound):
        resolve(root, "/nodir/missing", must_exist=False)
    with pytest.raises(NotFound):
        resolve(root, "/d/f.txt/deeper")
    assert resolve(root, "/d/new", must_exist=False).real == root / "d" / "new"


def test_resolve_rejects_symlinks(tmp_path):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("secret")
    try:
        (root / "link").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not available")
    with pytest.raises(PathError):
        resolve(root, "/link")
    with pytest.raises(PathError):
        resolve(root, "/link/secret.txt")


def test_resolve_rejects_a_symlink_component_even_when_symlinks_cannot_be_created(tmp_path, monkeypatch):
    """Simulate a link with lstat, so the check also runs on platforms where tests cannot create links."""
    import os
    import stat

    from app import paths

    root = tmp_path / "root"
    (root / "link").mkdir(parents=True)
    real_lstat = os.lstat

    def fake(path, *args, **kwargs):
        info = real_lstat(path, *args, **kwargs)
        if str(path).endswith("link"):
            values = list(info)
            values[0] = stat.S_IFLNK | 0o777
            return os.stat_result(values)
        return info

    monkeypatch.setattr(paths.os, "lstat", fake)
    with pytest.raises(PathError):
        resolve(root, "/link")
    with pytest.raises(PathError):
        resolve(root, "/link/x", must_exist=False)


def test_resolve_rejects_real_path_escaping_the_root(tmp_path, monkeypatch):
    from app import paths

    root = tmp_path / "root"
    root.mkdir()
    (root / "d").mkdir()
    monkeypatch.setattr(paths.os.path, "realpath", lambda p: str(tmp_path / "elsewhere") if str(p).endswith("d") else str(root))
    with pytest.raises(PathError):
        resolve(root, "/d")


def test_resolve_survives_other_oserrors(tmp_path, monkeypatch):
    from app import paths

    root = tmp_path / "root"
    root.mkdir()

    def broken(*args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(paths.os, "lstat", broken)
    with pytest.raises(PathError):
        resolve(root, "/x")
