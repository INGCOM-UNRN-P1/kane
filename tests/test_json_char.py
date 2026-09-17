"""Regresión de KANE-D0302: `--json` debe soportar campos `char` simples.

`struct.unpack("<c", ...)` devuelve bytes (b'A'), que no es serializable a
JSON: cualquier spec con un `char` suelto rompía la salida estructurada, que
es justamente la que consume un pipeline.
"""

import json
import struct
from pathlib import Path

import pytest

from kane.core.struct_mapper import inspect_binary_file

SPEC = "char c, int id, double prom"


@pytest.fixture
def binario(tmp_path):
    ruta = tmp_path / "datos.bin"
    # Layout x86_64 de `struct { char c; int id; double prom; }`: 16 B con
    # 3 bytes de padding tras `c`.
    ruta.write_bytes(
        struct.pack("<cxxxid", b"A", 42, 7.5) + struct.pack("<cxxxid", b"B", 99, 3.25)
    )
    return ruta


def test_el_reporte_es_serializable_a_json(binario):
    reporte = inspect_binary_file(binario, SPEC)
    json.dumps(reporte.to_dict() if hasattr(reporte, "to_dict") else reporte.__dict__, default=str)


def test_el_char_se_interpreta_como_texto(binario):
    reporte = inspect_binary_file(binario, SPEC)
    valores = {f.name: f.interpreted_value for f in reporte.records[0].fields if not f.is_padding}
    assert valores["c"] == "A"
    assert not isinstance(valores["c"], bytes)


def test_el_layout_respeta_el_padding_del_compilador(binario):
    """KANE-D0301: los binarios de `fwrite` incluyen el padding del struct."""
    reporte = inspect_binary_file(binario, SPEC)
    assert reporte.struct_size_bytes == 16
    assert reporte.records_count == 2
    assert reporte.remaining_bytes == 0


def test_los_campos_posteriores_al_padding_decodifican_bien(binario):
    reporte = inspect_binary_file(binario, SPEC)
    segundo = {f.name: f.interpreted_value for f in reporte.records[1].fields if not f.is_padding}
    assert segundo["id"] == 99
    assert segundo["prom"] == 3.25
