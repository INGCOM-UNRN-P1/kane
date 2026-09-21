"""Tests unitarios y de integración para KANE."""

import json
import struct
from pathlib import Path
from typer.testing import CliRunner
from kane.cli import app
from kane.core.struct_mapper import inspect_binary_file
from kane.plugins.ripley_plugin import KanePlugin

runner = CliRunner()


def test_cli_doctor():
    res = runner.invoke(app, ["doctor"])
    assert res.exit_code == 0
    assert "doctor" in res.output.lower()

    res_json = runner.invoke(app, ["doctor", "--json"])
    assert res_json.exit_code == 0
    data = json.loads(res_json.output)
    assert data["herramienta"] == "kane"
    assert data["ok"] is True


def test_inspect_binary_with_struct(tmp_path):
    bin_file = tmp_path / "alumnos.bin"
    # Escribir 2 registros: int id (4B), float nota (4B)
    data = struct.pack("<if", 101, 8.5) + struct.pack("<if", 102, 9.0)
    bin_file.write_bytes(data)

    report = inspect_binary_file(bin_file, "int id, float nota")
    assert report.records_count == 2
    assert report.struct_size_bytes == 8
    assert report.records[0].fields[0].interpreted_value == 101
    assert round(report.records[0].fields[1].interpreted_value, 1) == 8.5


def test_cli_inspect_json(tmp_path):
    bin_file = tmp_path / "datos.bin"
    bin_file.write_bytes(struct.pack("<i", 42))
    res = runner.invoke(app, ["inspect", str(bin_file), "-s", "int valor", "--json"])
    assert res.exit_code == 0
    assert '"records_count": 1' in res.output


def test_cli_version():
    assert runner.invoke(app, ["version"]).exit_code != 0  # KANE-D0403: ya no es subcomando
    res = runner.invoke(app, ["--version"])
    assert res.exit_code == 0
    assert "KANE" in res.output


def test_ripley_plugin(tmp_path):
    bin_file = tmp_path / "archivo.bin"
    bin_file.write_bytes(b"\x00" * 16)
    plugin = KanePlugin()
    res = plugin.run({"source_dir": str(tmp_path)})
    assert res["passed"] is True
    assert res["binary_files_count"] == 1


def test_inspect_binary_with_padding(tmp_path):
    bin_file = tmp_path / "padding.bin"
    # char c (1B) + 3B padding + int id (4B) = 8B
    data = struct.pack("<c3s i", b"X", b"\x00\x00\x00", 12345)
    bin_file.write_bytes(data)

    report = inspect_binary_file(bin_file, "char c, int id")
    assert report.records_count == 1
    assert report.struct_size_bytes == 8
    assert report.has_alignment_padding is True
    # Se interpreta como texto, no como bytes: `bytes` no es serializable
    # a JSON y rompía `--json` (KANE-D0302).
    assert report.records[0].fields[0].interpreted_value == "X"
    assert report.records[0].fields[1].name == "_pad_1"
    assert report.records[0].fields[1].is_padding is True
    assert report.records[0].fields[2].name == "id"
    assert report.records[0].fields[2].interpreted_value == 12345



def test_exit_code_refleja_bytes_residuales(tmp_path):
    """KANE-D0402: `passed` (sin bytes que no completan un registro) condiciona el exit code."""
    completo = tmp_path / "ok.bin"
    completo.write_bytes(struct.pack("<i", 1) + struct.pack("<i", 2))
    truncado = tmp_path / "trunc.bin"
    truncado.write_bytes(struct.pack("<i", 1) + b"\x01\x02")

    for extra in ([], ["--json"], ["--md", str(tmp_path / "o.md")]):
        assert runner.invoke(app, ["inspect", str(completo), "-s", "int v", *extra]).exit_code == 0, extra
        assert runner.invoke(app, ["inspect", str(truncado), "-s", "int v", *extra]).exit_code == 1, extra
    assert runner.invoke(app, ["report", str(completo), "-s", "int v"]).exit_code == 0
    assert runner.invoke(app, ["report", str(truncado), "-s", "int v"]).exit_code == 1
    # sin struct: volcado hex, no hay nada que "completar"
    assert runner.invoke(app, ["inspect", str(truncado)]).exit_code == 0
