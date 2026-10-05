"""`kane diff` (QoL #554) y el layout tomado de brett."""

import json
import struct
from pathlib import Path

from typer.testing import CliRunner

from kane.cli import app
from kane.core.struct_mapper import _calcular_layout, parse_struct_spec

runner = CliRunner()
SPEC = "int id, char nombre[8], double nota"


def _grabar(ruta: Path, registros) -> Path:
    datos = b""
    for id_, nombre, nota in registros:
        # int (4) + char[8] (8) + relleno (4) + double (8) = 24 B
        datos += struct.pack("<i8s4xd", id_, nombre.encode(), nota)
    ruta.write_bytes(datos)
    return ruta


def test_layout_con_los_offsets_de_brett():
    items, total, relleno = _calcular_layout(parse_struct_spec(SPEC))
    assert total == 24 and relleno
    assert [(n, off, tam, pad) for _, n, off, tam, pad in items] == [
        ("id", 0, 4, False), ("nombre", 4, 8, False), ("_pad_12", 12, 4, True), ("nota", 16, 8, False)]


def test_diff_campo_por_campo(tmp_path):
    a = _grabar(tmp_path / "a.bin", [(1, "ana", 7.5), (2, "luis", 4.0)])
    b = _grabar(tmp_path / "b.bin", [(1, "ana", 8.0), (2, "luis", 4.0)])
    res = runner.invoke(app, ["diff", str(a), str(b), "--struct", SPEC, "--json"])
    datos = json.loads(res.stdout)
    assert res.exit_code == 1
    assert datos["diferencias"] == [{"registro": 1, "campo": "nota", "tipo": "double", "offset": 16,
                                     "valor_a": 7.5, "valor_b": 8.0}]


def test_diff_iguales_y_relleno_ignorado(tmp_path):
    a = _grabar(tmp_path / "a.bin", [(1, "ana", 7.5)])
    b = tmp_path / "b.bin"
    crudo = bytearray(a.read_bytes())
    crudo[12:16] = b"\xff\xff\xff\xff"  # basura en el relleno: no es una diferencia
    b.write_bytes(bytes(crudo))
    assert runner.invoke(app, ["diff", str(a), str(b), "--struct", SPEC]).exit_code == 0
    assert runner.invoke(app, ["diff", str(a), str(b)]).exit_code == 2
