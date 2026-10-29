"""Tamaños y alineaciones por ABI desde brett (`brett.core.layout.ABIS`) y `--abi` (Ola 28)."""

import json
import shutil
import struct
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from kane.cli import app
from kane.core.struct_mapper import EspecificacionInvalida, inspect_binary_file, parse_struct_spec

SPEC = "char c, double d, long l, int i"
runner = CliRunner()


def _campos(reporte, registro=0):
    return {f.name: f for f in reporte.records[registro].fields if not f.is_padding}


def test_long_y_double_cambian_segun_la_abi():
    por_abi = {abi: {c.nombre: (c.tamanio, c.alineacion) for c in parse_struct_spec(SPEC, abi=abi)}
               for abi in ("x86_64", "x86_64-windows", "i386")}
    assert por_abi["x86_64"]["l"] == (8, 8)
    assert por_abi["x86_64-windows"]["l"] == (4, 4)
    assert por_abi["i386"]["d"] == (8, 4)          # double de 8 bytes alineado a 4


@pytest.mark.parametrize("abi, formato, offsets, total", [
    # System V i386: double alineado a 4, long de 4.
    ("i386", "<c3xdli", {"c": 0, "d": 4, "l": 12, "i": 16}, 20),
    # MinGW-w64 (MSYS2 UCRT64): LLP64, long de 4.
    ("x86_64-windows", "<c7xdli", {"c": 0, "d": 8, "l": 16, "i": 20}, 24),
])
def test_lee_registros_escritos_en_otra_abi(tmp_path, abi, formato, offsets, total):
    assert struct.calcsize(formato) == total
    binario = tmp_path / "r.bin"
    binario.write_bytes(struct.pack(formato, b"A", 1.5, -7, 42) + struct.pack(formato, b"B", 2.25, 123456, -1))
    reporte = inspect_binary_file(binario, SPEC, abi=abi)
    assert reporte.struct_size_bytes == total and reporte.records_count == 2 and reporte.remaining_bytes == 0
    assert reporte.abi == abi
    campos = _campos(reporte, 1)
    assert {n: f.offset - total for n, f in campos.items()} == offsets
    assert [campos[n].interpreted_value for n in "cdli"] == ["B", 2.25, 123456, -1]
    # Con la ABI equivocada, el mismo archivo no cierra en registros enteros (o da otros valores).
    otra = inspect_binary_file(binario, SPEC)
    assert otra.struct_size_bytes != total


@pytest.mark.skipif(shutil.which("gcc") is None, reason="requiere gcc")
def test_x86_64_coincide_con_gcc(tmp_path):
    fuente = tmp_path / "r.c"
    fuente.write_text(
        '#include <stdio.h>\n#include <stddef.h>\nstruct R { char c; double d; long l; int i; };\n'
        'int main(void){ struct R r = {\'A\', 1.5, -7, 42}; FILE *f = fopen("r.bin","wb"); fwrite(&r, sizeof r, 1, f);'
        ' fclose(f); printf("%zu %zu %zu %zu", sizeof r, offsetof(struct R,d), offsetof(struct R,l), offsetof(struct R,i));'
        ' return 0; }\n', encoding="utf-8")
    subprocess.run(["gcc", str(fuente), "-o", str(tmp_path / "r")], check=True)
    salida = subprocess.run([str(tmp_path / "r")], cwd=tmp_path, capture_output=True, text=True, check=True).stdout
    total, d, l, i = map(int, salida.split())
    reporte = inspect_binary_file(tmp_path / "r.bin", SPEC, abi="x86_64")
    campos = _campos(reporte)
    assert reporte.struct_size_bytes == total
    assert (campos["d"].offset, campos["l"].offset, campos["i"].offset) == (d, l, i)
    assert [campos[n].interpreted_value for n in "cdli"] == ["A", 1.5, -7, 42]


def test_abi_desconocida_y_cli(tmp_path):
    with pytest.raises(EspecificacionInvalida, match="ABI desconocida 'sparc'"):
        parse_struct_spec("int x", abi="sparc")
    binario = tmp_path / "r.bin"
    binario.write_bytes(struct.pack("<c3xdli", b"A", 1.5, -7, 42))
    res = runner.invoke(app, ["inspect", str(binario), "--struct", SPEC, "--abi", "i386", "--json"])
    assert res.exit_code == 0, res.output
    datos = json.loads(res.output)
    assert datos["abi"] == "i386" and datos["struct_size_bytes"] == 20
    assert runner.invoke(app, ["inspect", str(binario), "--struct", SPEC, "--abi", "sparc"]).exit_code == 2
