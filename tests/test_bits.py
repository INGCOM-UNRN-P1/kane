"""kane bits: representación de bits de valores de C (revisión 05 §3, «representación de bits»)."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from kane.cli import app
from kane.core.bits import (
    ValorInvalido,
    evaluar_bits,
    interpretar_literal,
    representar_entero,
    representar_flotante,
    tipo_c,
)

runner = CliRunner()


def test_complemento_a_dos_y_desborde():
    r = representar_entero(-1, tipo_c("int8_t"))
    assert (r.binario, r.hexadecimal, r.sin_signo, r.desborda) == ("11111111", "0xFF", 255, False)
    r = representar_entero(300, tipo_c("uint8_t"))
    assert (r.valor_guardado, r.desborda) == (44, True)
    r = representar_entero(128, tipo_c("signed char"))
    assert r.valor_guardado == -128 and r.desborda


def test_bytes_en_memoria_segun_el_orden():
    assert representar_entero(0x12345678, tipo_c("int")).bytes_en_memoria == ["78", "56", "34", "12"]
    assert representar_entero(0x12345678, tipo_c("int"), "big").bytes_en_memoria == ["12", "34", "56", "78"]


@pytest.mark.parametrize("valor, clase, exponente", [
    (1.0, "normal", 0), (0.1, "normal", -4), (0.0, "cero", None),
    (float("inf"), "infinito", None), (1e-45, "subnormal", -126),
])
def test_ieee_754_float(valor, clase, exponente):
    r = representar_flotante(valor, tipo_c("float"))
    assert (r.clase, r.exponente) == (clase, exponente)
    assert len(r.exponente_bits) == 8 and len(r.mantisa_bits) == 23


def test_double_y_valores_inexactos():
    r = representar_flotante(0.1, tipo_c("double"))
    assert r.hexadecimal == "0x3FB999999999999A" and len(r.mantisa_bits) == 52
    assert any("no tiene representación exacta" in linea for linea in representar_flotante(0.1, tipo_c("float")).explicacion)


@pytest.mark.parametrize("texto, esperado", [
    ("42", 42), ("-7", -7), ("0x2A", 42), ("0b101010", 42), ("052", 42), ("'A'", 65), ("42u", 42), ("3.5", 3.5),
])
def test_literales_de_c(texto, esperado):
    assert interpretar_literal(texto) == esperado


def test_operaciones_de_bits_paso_a_paso():
    resultado, pasos = evaluar_bits("0x0F & 0xF3", tipo_c("uint8_t"))
    assert resultado.valor_guardado == 3 and [p.operacion for p in pasos] == ["15 & 243"]
    resultado, _ = evaluar_bits("~0", tipo_c("uint8_t"))
    assert resultado.valor_guardado == 255
    resultado, _ = evaluar_bits("-16 >> 2", tipo_c("int"))
    assert resultado.valor_guardado == -4  # desplazamiento aritmético con signo
    resultado, _ = evaluar_bits("1 << 3 | 1", tipo_c("int"))
    assert resultado.valor_guardado == 9


def test_promocion_entera_de_los_tipos_chicos():
    # En C, unsigned char se promueve a int: 0xF3 << 2 es 972 (no 204) y >> 2 vuelve a 243.
    resultado, pasos = evaluar_bits("0xF3 << 2 >> 2", tipo_c("unsigned char"))
    assert resultado.valor_guardado == 243 and pasos[0].resultado.valor_guardado == 972
    assert pasos[0].resultado.bits_tipo == 32 and "Promoción entera" in resultado.explicacion[0]
    # ~ de un uint8_t promovido da un int negativo; >> lo desplaza con signo y queda 255 al guardarlo.
    resultado, _ = evaluar_bits("~0x0F >> 4", tipo_c("uint8_t"))
    assert resultado.valor_guardado == 255
    # Sin promoción (unsigned int), el >> es lógico.
    resultado, _ = evaluar_bits("~0x0F >> 4", tipo_c("uint32_t"))
    assert resultado.valor_guardado == 0x0FFFFFFF


def test_notas_de_comportamiento_indefinido():
    _, pasos = evaluar_bits("-8 << 1", tipo_c("int"))
    assert "negativo es comportamiento indefinido" in pasos[0].nota
    _, pasos = evaluar_bits("0x40000000 << 2", tipo_c("int"))
    assert "desborde con signo" in pasos[0].nota
    _, pasos = evaluar_bits("0x40000000 << 2", tipo_c("unsigned int"))
    assert pasos[0].nota == ""


def test_errores_de_uso():
    with pytest.raises(ValorInvalido, match="comportamiento indefinido"):
        evaluar_bits("1 << 40", tipo_c("int"))
    with pytest.raises(ValorInvalido, match="Windows"):
        tipo_c("long")
    with pytest.raises(ValorInvalido, match="literal"):
        interpretar_literal("hola")


def test_cli_negativo_json_y_error():
    res = runner.invoke(app, ["bits", "-1", "-t", "int8_t", "--json"])
    assert res.exit_code == 0, res.output
    datos = json.loads(res.stdout)
    assert datos["resultado"]["binario"] == "11111111" and datos["schema_version"] == "1.0.0"
    res = runner.invoke(app, ["bits", "3.5", "-t", "int"])
    assert res.exit_code == 2 and "float o double" in res.output
