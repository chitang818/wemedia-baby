from scripts.maintenance.check_text_encoding import (
    find_non_utf8_files,
    iter_text_files,
    main,
)


def test_find_non_utf8_files_reports_text_decode_failures(tmp_path):
    good = tmp_path / "good.py"
    bad = tmp_path / "bad.py"
    binary = tmp_path / "image.bin"

    good.write_text("print('ok')\n", encoding="utf-8")
    bad.write_bytes(b"\xff\xfe\x00")
    binary.write_bytes(b"\xff\xfe\x00")

    assert find_non_utf8_files(tmp_path) == [bad]


def test_iter_text_files_skips_generated_directories(tmp_path):
    generated = tmp_path / "__pycache__" / "bad.py"
    generated.parent.mkdir()
    generated.write_bytes(b"\xff")
    normal = tmp_path / "normal.json"
    normal.write_text("{}", encoding="utf-8")

    assert list(iter_text_files(tmp_path)) == [normal]


def test_cli_returns_failure_when_non_utf8_text_exists(tmp_path, capsys):
    bad = tmp_path / "bad.md"
    bad.write_bytes(b"\xff")

    assert main([str(tmp_path)]) == 1
    assert "bad.md" in capsys.readouterr().err
