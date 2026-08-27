"""Tests unitarios y de integración para KANE."""

import struct
from pathlib import Path
from typer.testing import CliRunner
from kane.cli import app
from kane.core.struct_mapper import inspect_binary_file
from kane.plugins.ripley_plugin import KanePlugin

runner = CliRunner()


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
    res = runner.invoke(app, ["version"])
    assert res.exit_code == 0
    assert "KANE" in res.output


def test_ripley_plugin(tmp_path):
    bin_file = tmp_path / "archivo.bin"
    bin_file.write_bytes(b"\x00" * 16)
    plugin = KanePlugin()
    res = plugin.run({"source_dir": str(tmp_path)})
    assert res["passed"] is True
    assert res["binary_files_count"] == 1
