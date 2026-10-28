"""Ola 18 (QoL #548, #554): `kane inspect --header` dice qué revela el archivo del programa que lo
escribió: registro truncado, desalineación, relleno con basura y cadenas sin terminador."""

import json
import struct
from pathlib import Path

import pytest
from typer.testing import CliRunner

from kane.cli import app

runner = CliRunner()
HEADER = """typedef struct
{
    char inicial;
    int legajo;
    char nombre[6];
    double nota;
} registro_t;
"""
# Con relleno (como lo escribe fwrite del struct): c, 3 de relleno, int, char[6], 2 de relleno, double = 24 B.
REGISTRO = "<c3si6s2sd"


def _registro(inicial=b"A", legajo=1, nombre=b"Ana\0\0\0", nota=7.5, relleno=b"\0"):
    return struct.pack(REGISTRO, inicial, relleno * 3, legajo, nombre, relleno * 2, nota)


def _inspeccionar(tmp_path: Path, contenido: bytes):
    (tmp_path / "reg.h").write_text(HEADER, encoding="utf-8")
    archivo = tmp_path / "datos.bin"
    archivo.write_bytes(contenido)
    res = runner.invoke(app, ["inspect", str(archivo), "-H", str(tmp_path / "reg.h"), "--json"])
    datos = json.loads(res.stdout)
    return res.exit_code, datos, {h["codigo"]: h for h in datos["hallazgos"]}


def test_archivo_bien_escrito(tmp_path):
    codigo, datos, hallazgos = _inspeccionar(tmp_path, _registro() * 3)
    assert (codigo, datos["records_count"], hallazgos) == (0, 3, {})


def test_registro_truncado(tmp_path):
    codigo, datos, hallazgos = _inspeccionar(tmp_path, _registro() + _registro()[:10])
    assert codigo == 1 and set(hallazgos) == {"KANE001"}
    h = hallazgos["KANE001"]
    assert (h["registro"], h["offset"], h["campo"]) == (2, 24, "nombre")
    assert "llegaron enteros inicial, legajo y 'nombre' quedó truncado (2 de 6 B)" in h["mensaje"]


def test_escrito_campo_por_campo(tmp_path):
    sin_relleno = struct.pack("<ci6sd", b"A", 1, b"Ana\0\0\0", 7.5)
    codigo, _, hallazgos = _inspeccionar(tmp_path, sin_relleno * 3)
    assert codigo == 1 and set(hallazgos) == {"KANE003"}  # sin falsos KANE002 de registros corridos
    assert "sus campos sin relleno (19 B, 3 registros)" in hallazgos["KANE003"]["mensaje"]


def test_relleno_con_basura(tmp_path):
    codigo, _, hallazgos = _inspeccionar(tmp_path, _registro() + _registro(relleno=b"\xab"))
    assert codigo == 0  # es una advertencia
    h = hallazgos["KANE002"]
    assert (h["severidad"], h["registro"], h["offset"]) == ("advertencia", 2, 25)
    assert "En 1 de 2 registros" in h["mensaje"] and "= {0}" in h["sugerencia"]


def test_cadena_sin_terminador(tmp_path):
    _, _, hallazgos = _inspeccionar(tmp_path, _registro(nombre=b"Bartol"))
    h = hallazgos["KANE004"]
    assert h["campo"] == "nombre" and "nombre[5] = '\\0';" in h["sugerencia"]


@pytest.mark.parametrize("contenido, aviso", [
    (_registro() + _registro()[:10], "KANE001"),
    (_registro(relleno=b"\x01"), "KANE002"),
])
def test_markdown_y_texto(tmp_path, contenido, aviso):
    (tmp_path / "reg.h").write_text(HEADER, encoding="utf-8")
    (tmp_path / "d.bin").write_bytes(contenido)
    md = tmp_path / "kane.md"
    runner.invoke(app, ["inspect", str(tmp_path / "d.bin"), "-H", str(tmp_path / "reg.h"), "--md", str(md)])
    assert f"**{aviso}:**" in md.read_text(encoding="utf-8")
    res = runner.invoke(app, ["inspect", str(tmp_path / "d.bin"), "-H", str(tmp_path / "reg.h")])
    assert aviso in res.stdout
