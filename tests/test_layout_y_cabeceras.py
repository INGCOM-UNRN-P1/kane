"""Regresión de KANE-D0303, D0304 y D0305.

D0303: el orden de bytes estaba fijo en little-endian sin flag; el README
       prometía "detección y visualización" de endianness.
D0304: el README prometía mapear structs de cabeceras `.h`, pero solo se
       aceptaba la cadena ad-hoc de `--struct`.
D0305: `int arr[3]` se leía como `char[3]`, `unsigned char` ocupaba 4 bytes y
       un tipo desconocido caía en silencio a `int`.
"""

import json
import shutil
import struct
import subprocess
import textwrap

import pytest
from typer.testing import CliRunner

from kane.cli import app
from kane.core.struct_mapper import (
    EspecificacionInvalida,
    inspect_binary_file,
    parse_struct_spec,
    struct_de_cabecera,
)

runner = CliRunner()

CABECERA = textwrap.dedent(
    """\
    #ifndef ALUMNO_H
    #define ALUMNO_H
    #define MAX_NOMBRE 12
    /* registro de alumno: struct falso { int x; } en un comentario */
    typedef struct {
        unsigned char activo;   // flag
        int legajo;
        char nombre[MAX_NOMBRE];
        short notas[3];
        double promedio;
    } Alumno;
    typedef struct Punto { int x, y; } Punto;
    struct Malo { struct Punto p; int z; };
    #endif
    """
)

necesita_gcc = pytest.mark.skipif(shutil.which("gcc") is None, reason="requiere gcc para el layout real")


@pytest.fixture
def cabecera(tmp_path):
    ruta = tmp_path / "alumno.h"
    ruta.write_text(CABECERA, encoding="utf-8")
    return ruta


def _campos(reporte, indice=0):
    return {f.name: f for f in reporte.records[indice].fields}


# --- D0305: tipos y arreglos ------------------------------------------------

def test_un_arreglo_de_enteros_no_se_reinterpreta_como_char():
    campo = parse_struct_spec("int arr[3]")[0]
    assert campo.tipo == "int" and campo.cantidad == 3
    assert campo.tamanio == 12 and campo.alineacion == 4


def test_los_elementos_de_un_arreglo_se_decodifican_uno_a_uno(tmp_path):
    ruta = tmp_path / "a.bin"
    ruta.write_bytes(struct.pack("<3i", 1, -2, 300))
    reporte = inspect_binary_file(ruta, "int arr[3]")
    assert _campos(reporte)["arr"].interpreted_value == [1, -2, 300]
    assert _campos(reporte)["arr"].type_name == "int[3]"


@pytest.mark.parametrize(
    "tipo, esperado",
    [
        ("unsigned char", 1), ("signed char", 1), ("short int", 2), ("unsigned short", 2),
        ("unsigned int", 4), ("unsigned", 4), ("long", 8), ("long int", 8), ("long long", 8),
        ("unsigned long long", 8), ("int64_t", 8), ("uint8_t", 1), ("size_t", 8), ("_Bool", 1),
        ("float", 4), ("double", 8), ("enum Color", 4),
    ],
)
def test_el_tamanio_de_cada_tipo_es_el_del_abi_lp64(tipo, esperado):
    assert parse_struct_spec(f"{tipo} x")[0].tamanio == esperado


def test_un_unsigned_se_decodifica_sin_signo(tmp_path):
    ruta = tmp_path / "u.bin"
    ruta.write_bytes(struct.pack("<I", 0xFFFFFFFF))
    assert _campos(inspect_binary_file(ruta, "unsigned int v"))["v"].interpreted_value == 4294967295
    ruta.write_bytes(struct.pack("<i", -1))
    assert _campos(inspect_binary_file(ruta, "int v"))["v"].interpreted_value == -1


@pytest.mark.parametrize(
    "spec",
    [
        "Fecha f",            # tipo desconocido: antes caía a int
        "char *nombre",       # puntero
        "int m[2][3]",        # multidimensional
        "int v[N]",           # dimensión simbólica sin #define
        "int v[0]",           # dimensión nula
        "long double x",      # 80 bits
        "struct Punto p",     # anidado
        "int a, int a",       # nombre repetido
        "int",                # falta el nombre
        "unsigned float x",
        "",
    ],
)
def test_lo_que_no_se_puede_mapear_falla_con_un_mensaje_en_vez_de_adivinar(spec):
    with pytest.raises(EspecificacionInvalida):
        parse_struct_spec(spec)


# --- D0303: orden de bytes --------------------------------------------------

def test_el_orden_de_bytes_por_defecto_es_little_endian(tmp_path):
    ruta = tmp_path / "e.bin"
    ruta.write_bytes(bytes([0x01, 0x02, 0x00, 0x00]))
    reporte = inspect_binary_file(ruta, "int v")
    assert _campos(reporte)["v"].interpreted_value == 0x0201
    assert reporte.byte_order == "little"


def test_big_endian_lee_los_mismos_bytes_en_orden_inverso(tmp_path):
    ruta = tmp_path / "e.bin"
    ruta.write_bytes(bytes([0x00, 0x00, 0x01, 0x02]))
    reporte = inspect_binary_file(ruta, "int v", endian="big")
    assert _campos(reporte)["v"].interpreted_value == 0x0102
    assert reporte.byte_order == "big"


def test_endian_afecta_tambien_a_los_elementos_de_un_arreglo(tmp_path):
    ruta = tmp_path / "e.bin"
    ruta.write_bytes(struct.pack(">3h", 1, 2, 3))
    assert _campos(inspect_binary_file(ruta, "short v[3]", endian="big"))["v"].interpreted_value == [1, 2, 3]


def test_un_orden_de_bytes_invalido_se_rechaza(tmp_path):
    ruta = tmp_path / "e.bin"
    ruta.write_bytes(b"\x00" * 4)
    with pytest.raises(EspecificacionInvalida):
        inspect_binary_file(ruta, "int v", endian="middle")
    res = runner.invoke(app, ["inspect", str(ruta), "-s", "int v", "--endian", "middle"])
    assert res.exit_code == 2


def test_el_cli_expone_endian_en_json(tmp_path):
    ruta = tmp_path / "e.bin"
    ruta.write_bytes(bytes([0x00, 0x00, 0x01, 0x02]))
    res = runner.invoke(app, ["inspect", str(ruta), "-s", "int v", "--endian", "big", "--json"])
    assert res.exit_code == 0
    datos = json.loads(res.output)
    assert datos["byte_order"] == "big"
    assert datos["records"][0]["fields"][0]["interpreted_value"] == 0x0102


# --- D0304: cabeceras .h ----------------------------------------------------

def test_un_struct_typedef_anonimo_se_lee_de_la_cabecera(cabecera):
    nombre, spec = struct_de_cabecera(cabecera, "Alumno")
    assert nombre == "Alumno"
    assert spec == "unsigned char activo, int legajo, char nombre[12], short notas[3], double promedio"


def test_los_comentarios_de_la_cabecera_no_inventan_structs(cabecera):
    with pytest.raises(EspecificacionInvalida) as exc:
        struct_de_cabecera(cabecera, "falso")
    assert "Alumno" in str(exc.value) and "Punto" in str(exc.value)


def test_un_declarador_multiple_comparte_el_tipo(cabecera):
    assert struct_de_cabecera(cabecera, "Punto")[1] == "int x, int y"


def test_una_cabecera_con_varios_structs_exige_el_nombre(cabecera):
    with pytest.raises(EspecificacionInvalida) as exc:
        struct_de_cabecera(cabecera)
    assert "--name" in str(exc.value)


def test_una_cabecera_con_un_solo_struct_no_pide_nombre(tmp_path):
    h = tmp_path / "uno.h"
    h.write_text("struct Reg { int id; float nota; };", encoding="utf-8")
    assert struct_de_cabecera(h) == ("Reg", "int id, float nota")


def test_un_struct_anidado_se_informa_pero_no_impide_usar_los_demas(cabecera):
    with pytest.raises(EspecificacionInvalida) as exc:
        struct_de_cabecera(cabecera, "Malo")
    assert "Malo" in str(exc.value)
    assert struct_de_cabecera(cabecera, "Punto")[1] == "int x, int y"


def test_una_cabecera_sin_structs_falla(tmp_path):
    h = tmp_path / "vacia.h"
    h.write_text("int sumar(int a, int b);\n", encoding="utf-8")
    with pytest.raises(EspecificacionInvalida):
        struct_de_cabecera(h)


def test_typedef_con_etiqueta_responde_a_ambos_nombres(tmp_path):
    h = tmp_path / "t.h"
    h.write_text("typedef struct Nodo_s { int v; } Nodo;", encoding="utf-8")
    assert struct_de_cabecera(h, "Nodo") == ("Nodo", "int v")
    assert struct_de_cabecera(h, "Nodo_s") == ("Nodo_s", "int v")


@necesita_gcc
def test_el_layout_coincide_con_el_de_gcc(tmp_path, cabecera):
    """La fuente de verdad del layout es el compilador, no otra herramienta del ecosistema."""
    prog = tmp_path / "l.c"
    prog.write_text(
        '#include <stdio.h>\n#include <stddef.h>\n#include "alumno.h"\n'
        "int main(void) {\n"
        '  printf("%zu %zu %zu %zu %zu %zu\\n", sizeof(Alumno), offsetof(Alumno, activo),'
        " offsetof(Alumno, legajo), offsetof(Alumno, nombre), offsetof(Alumno, notas),"
        " offsetof(Alumno, promedio));\n  return 0;\n}\n",
        encoding="utf-8",
    )
    exe = tmp_path / "l"
    subprocess.run(["gcc", "-o", str(exe), str(prog)], check=True)
    tam, *offsets = map(int, subprocess.run([str(exe)], capture_output=True, text=True, check=True).stdout.split())

    _, spec = struct_de_cabecera(cabecera, "Alumno")
    binario = tmp_path / "a.bin"
    binario.write_bytes(b"\x00" * tam)
    reporte = inspect_binary_file(binario, spec)
    campos = _campos(reporte)
    assert reporte.struct_size_bytes == tam
    assert [campos[n].offset for n in ("activo", "legajo", "nombre", "notas", "promedio")] == offsets


def test_el_cli_mapea_un_binario_con_la_cabecera(tmp_path, cabecera):
    fila = struct.pack("<Bxxxi12s3hxxxxxxd", 1, 1234, b"Ana".ljust(12, b"\0"), 8, 9, 10, 9.0)
    binario = tmp_path / "alumnos.bin"
    binario.write_bytes(fila * 2)
    res = runner.invoke(
        app, ["inspect", str(binario), "--header", str(cabecera), "--name", "Alumno", "--json"]
    )
    assert res.exit_code == 0, res.output
    datos = json.loads(res.stdout)  # el aviso de origen va por stderr: stdout sigue siendo JSON puro
    assert datos["records_count"] == 2 and datos["struct_size_bytes"] == 40
    campos = {f["name"]: f["interpreted_value"] for f in datos["records"][1]["fields"] if not f["is_padding"]}
    assert campos == {
        "activo": 1, "legajo": 1234, "nombre": "Ana", "notas": [8, 9, 10], "promedio": 9.0,
    }


def test_el_cli_rechaza_struct_y_header_juntos(tmp_path, cabecera):
    binario = tmp_path / "x.bin"
    binario.write_bytes(b"\x00" * 8)
    res = runner.invoke(app, ["inspect", str(binario), "-s", "int a", "--header", str(cabecera), "-n", "Punto"])
    assert res.exit_code == 2


def test_el_cli_rechaza_name_sin_header(tmp_path):
    binario = tmp_path / "x.bin"
    binario.write_bytes(b"\x00" * 8)
    assert runner.invoke(app, ["inspect", str(binario), "-s", "int a", "--name", "X"]).exit_code == 2


def test_el_cli_falla_con_exit_2_ante_una_spec_invalida(tmp_path):
    binario = tmp_path / "x.bin"
    binario.write_bytes(b"\x00" * 8)
    res = runner.invoke(app, ["inspect", str(binario), "-s", "Fecha f"])
    assert res.exit_code == 2
    assert "Fecha" in res.output


def test_el_reporte_markdown_incluye_struct_y_orden_de_bytes(tmp_path, cabecera):
    binario = tmp_path / "x.bin"
    binario.write_bytes(struct.pack(">ii", 1, 2))
    salida = tmp_path / "r.md"
    res = runner.invoke(
        app, ["report", str(binario), "-H", str(cabecera), "-n", "Punto", "-e", "big", "-o", str(salida)]
    )
    assert res.exit_code == 0, res.output
    md = salida.read_text(encoding="utf-8")
    assert "big-endian" in md and "int x, int y" in md
