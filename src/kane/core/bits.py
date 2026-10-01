"""Representación de bits de valores de C: enteros con y sin signo, float y double (`kane bits`).

Cubre el gap de «representación de bits» (revisión, 05 §3; la propuesta `cypher` del histórico):
cómo queda guardado un valor en un tipo de C, qué pasa cuando no entra (aritmética modular), el
complemento a dos de los negativos, el desglose IEEE 754 de los flotantes y las operaciones de bits
(&, |, ^, ~, <<, >>) paso a paso, con los operandos alineados bit a bit.
"""

from __future__ import annotations

import ast
import math
import re
import struct
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple


class ValorInvalido(ValueError):
    """El valor o la expresión no se pueden interpretar en el tipo pedido."""


@dataclass(frozen=True)
class TipoC:
    nombre: str
    bits: int
    con_signo: bool
    flotante: bool = False


_TIPOS: List[TipoC] = [
    TipoC("char", 8, True), TipoC("signed char", 8, True), TipoC("unsigned char", 8, False),
    TipoC("short", 16, True), TipoC("unsigned short", 16, False),
    TipoC("int", 32, True), TipoC("unsigned int", 32, False), TipoC("unsigned", 32, False),
    TipoC("long long", 64, True), TipoC("unsigned long long", 64, False),
    TipoC("int8_t", 8, True), TipoC("uint8_t", 8, False), TipoC("int16_t", 16, True), TipoC("uint16_t", 16, False),
    TipoC("int32_t", 32, True), TipoC("uint32_t", 32, False), TipoC("int64_t", 64, True), TipoC("uint64_t", 64, False),
    TipoC("size_t", 64, False),
    TipoC("float", 32, True, flotante=True), TipoC("double", 64, True, flotante=True),
]
TIPOS: Dict[str, TipoC] = {t.nombre: t for t in _TIPOS}
# `long` no está: mide 64 bits en Linux y macOS (LP64) pero 32 en Windows (LLP64).
NOTA_LONG = "`long` mide 64 bits en Linux y macOS pero 32 en Windows: usá int32_t o int64_t."


def tipo_c(nombre: str) -> TipoC:
    clave = " ".join(nombre.split())
    if clave in ("long", "unsigned long", "long int", "unsigned long int"):
        raise ValorInvalido(NOTA_LONG)
    if clave not in TIPOS:
        raise ValorInvalido(f"tipo desconocido: {nombre!r}. Tipos: {', '.join(TIPOS)}.")
    return TIPOS[clave]


def agrupar(bits: str, cada: int = 4) -> str:
    """'00101100' → '0010 1100' (de derecha a izquierda, como se leen los nibbles)."""
    grupos = []
    while bits:
        grupos.insert(0, bits[-cada:])
        bits = bits[:-cada]
    return " ".join(grupos)


@dataclass
class RepresentacionEntera:
    tipo: str
    bits_tipo: int
    valor_pedido: int
    valor_guardado: int
    sin_signo: int
    binario: str
    hexadecimal: str
    bytes_en_memoria: List[str]
    orden: str
    desborda: bool
    explicacion: List[str] = field(default_factory=list)

    def a_dict(self) -> dict:
        return asdict(self)


def representar_entero(valor: int, tipo: TipoC, orden: str = "little") -> RepresentacionEntera:
    """Cómo queda `valor` guardado en `tipo`: si no entra, se reduce módulo 2^n (como en C)."""
    n = tipo.bits
    patron = valor % (1 << n)  # el patrón de bits que queda en memoria
    guardado = patron - (1 << n) if tipo.con_signo and patron >= 1 << (n - 1) else patron
    minimo, maximo = (-(1 << (n - 1)), (1 << (n - 1)) - 1) if tipo.con_signo else (0, (1 << n) - 1)
    desborda = not minimo <= valor <= maximo
    binario = format(patron, f"0{n}b")
    crudos = patron.to_bytes(n // 8, "little" if orden == "little" else "big")
    explicacion = []
    if desborda:
        explicacion.append(
            f"{valor} no entra en {tipo.nombre} ({minimo} a {maximo}): se guarda {guardado}, "
            f"que es {valor} módulo 2^{n} = {patron}" + (f" leído con signo" if guardado != patron else "") + ".")
    if tipo.con_signo and guardado < 0:
        positivo = format(-guardado, f"0{n}b")
        invertido = "".join("1" if b == "0" else "0" for b in positivo)
        explicacion.append(
            f"Complemento a dos: |{guardado}| = {agrupar(positivo)}; se invierten los bits "
            f"({agrupar(invertido)}) y se suma 1: {agrupar(binario)}.")
    if tipo.con_signo:
        explicacion.append(f"El bit más significativo (el de la izquierda) es el signo: {binario[0]}.")
    explicacion.append(
        f"En memoria ({'little' if orden == 'little' else 'big'}-endian) los bytes van "
        + ("del menos significativo al más significativo." if orden == "little" else "del más significativo al menos significativo."))
    return RepresentacionEntera(
        tipo=tipo.nombre, bits_tipo=n, valor_pedido=valor, valor_guardado=guardado, sin_signo=patron,
        binario=binario, hexadecimal=f"0x{patron:0{n // 4}X}", bytes_en_memoria=[f"{b:02X}" for b in crudos],
        orden=orden, desborda=desborda, explicacion=explicacion)


@dataclass
class RepresentacionFlotante:
    tipo: str
    bits_tipo: int
    valor_pedido: str
    valor_guardado: str
    binario: str
    hexadecimal: str
    bytes_en_memoria: List[str]
    orden: str
    signo: str
    exponente_bits: str
    exponente: Optional[int]
    mantisa_bits: str
    clase: str
    explicacion: List[str] = field(default_factory=list)

    def a_dict(self) -> dict:
        return asdict(self)


def representar_flotante(valor: float, tipo: TipoC, orden: str = "little") -> RepresentacionFlotante:
    """Desglose IEEE 754 de `valor` como float (1 + 8 + 23 bits) o double (1 + 11 + 52 bits)."""
    formato, bits_exp, bits_man = ("f", 8, 23) if tipo.bits == 32 else ("d", 11, 52)
    try:
        crudos_big = struct.pack(">" + formato, valor)
    except OverflowError:
        crudos_big = struct.pack(">" + formato, math.copysign(math.inf, valor))
    patron = int.from_bytes(crudos_big, "big")
    binario = format(patron, f"0{tipo.bits}b")
    signo, exp_bits, man_bits = binario[0], binario[1:1 + bits_exp], binario[1 + bits_exp:]
    guardado = struct.unpack(">" + formato, crudos_big)[0]
    sesgo = (1 << (bits_exp - 1)) - 1
    e = int(exp_bits, 2)
    if e == 0 and int(man_bits, 2) == 0:
        clase, exponente = "cero", None
    elif e == 0:
        clase, exponente = "subnormal", 1 - sesgo
    elif e == (1 << bits_exp) - 1:
        clase, exponente = ("infinito" if int(man_bits, 2) == 0 else "nan"), None
    else:
        clase, exponente = "normal", e - sesgo
    explicacion = [f"IEEE 754 de {tipo.bits} bits: 1 bit de signo, {bits_exp} de exponente "
                   f"(sesgo {sesgo}) y {bits_man} de mantisa."]
    if clase == "normal":
        explicacion.append(f"Valor = (-1)^{signo} × 1.mantisa × 2^({e} - {sesgo}) = (-1)^{signo} × 1.mantisa × 2^{exponente}.")
    elif clase == "subnormal":
        explicacion.append(f"Subnormal (exponente todo en 0): valor = (-1)^{signo} × 0.mantisa × 2^{exponente}.")
    elif clase == "cero":
        explicacion.append("Cero: exponente y mantisa en 0 (el signo distingue +0 de -0).")
    elif clase == "infinito":
        explicacion.append("Infinito: exponente todo en 1 y mantisa en 0.")
    else:
        explicacion.append("NaN (no es un número): exponente todo en 1 y mantisa distinta de 0.")
    if clase in ("normal", "subnormal") and float(guardado) != valor and not math.isnan(valor):
        explicacion.append(f"{valor!r} no tiene representación exacta en binario: se guarda {guardado!r}.")
    crudos = crudos_big if orden == "big" else crudos_big[::-1]
    return RepresentacionFlotante(
        tipo=tipo.nombre, bits_tipo=tipo.bits, valor_pedido=repr(valor), valor_guardado=repr(guardado),
        binario=binario, hexadecimal=f"0x{patron:0{tipo.bits // 4}X}", bytes_en_memoria=[f"{b:02X}" for b in crudos],
        orden=orden, signo=signo, exponente_bits=exp_bits, exponente=exponente, mantisa_bits=man_bits,
        clase=clase, explicacion=explicacion)


def interpretar_literal(texto: str) -> int | float:
    """Literal de C: 42, -7, 0x2A, 0b101010, 052 (octal), 'A', 3.5, 1e-3."""
    t = texto.strip()
    if len(t) == 3 and t[0] == t[2] == "'":
        return ord(t[1])
    negativo = t.startswith("-")
    cuerpo = t[1:] if negativo or t.startswith("+") else t
    es_flotante = not cuerpo.lower().startswith("0x") and any(c in cuerpo.lower() for c in ".e")
    if not es_flotante:
        cuerpo = cuerpo.rstrip("uUlL")  # sufijos de entero de C: 42u, 7L, 3ULL
    try:
        if cuerpo.lower().startswith(("0x", "0b")):
            valor: int | float = int(cuerpo, 0)
        elif len(cuerpo) > 1 and cuerpo.startswith("0") and cuerpo.isdigit():
            valor = int(cuerpo, 8)  # en C, un 0 adelante es octal
        elif any(c in cuerpo.lower() for c in ".e") or cuerpo.lower() in ("inf", "nan", "infinity"):
            valor = float(cuerpo)
        else:
            valor = int(cuerpo, 10)
    except ValueError:
        raise ValorInvalido(f"no es un literal de C: {texto!r}") from None
    return -valor if negativo else valor


_OPERADORES = {ast.BitAnd: "&", ast.BitOr: "|", ast.BitXor: "^", ast.LShift: "<<", ast.RShift: ">>"}


@dataclass
class Paso:
    operacion: str
    operandos: List[RepresentacionEntera]
    resultado: RepresentacionEntera
    nota: str = ""


def _literales(expr: str) -> str:
    """0b/octal de C → Python: 052 es 42 en C (octal) y error de sintaxis en Python."""
    return re.sub(r"(?<![\w.])0([0-7]+)(?![\w.])", lambda m: str(int(m.group(1), 8)), expr)


def tipo_de_operacion(tipo: TipoC) -> TipoC:
    """Promoción entera: en C, char y short (con o sin signo) se convierten a int antes de operar."""
    return TIPOS["int"] if tipo.bits < TIPOS["int"].bits else tipo


def evaluar_bits(expr: str, tipo: TipoC, orden: str = "little") -> Tuple[RepresentacionEntera, List[Paso]]:
    """Evalúa una expresión de bits sobre valores de `tipo` y devuelve cada operación con sus operandos.

    Como en C, cada literal se toma como un valor de `tipo`; si `tipo` es más chico que int, se promueve
    a int y la operación se hace en 32 bits; el resultado final se guarda de vuelta en `tipo`.
    """
    if tipo.flotante:
        raise ValorInvalido("las operaciones de bits son de enteros: elegí un tipo entero.")
    try:
        arbol = ast.parse(_literales(expr), mode="eval")
    except SyntaxError:
        raise ValorInvalido(f"expresión inválida: {expr!r}") from None
    operacion = tipo_de_operacion(tipo)
    pasos: List[Paso] = []

    def en(valor: int) -> RepresentacionEntera:
        return representar_entero(valor, operacion, orden)

    def hoja(valor: int) -> int:
        # Un valor de `tipo` (como una variable declarada así), promovido al tipo de la operación.
        return representar_entero(valor, tipo, orden).valor_guardado

    def valor(nodo: ast.AST) -> int:
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, int) and not isinstance(nodo.value, bool):
            return hoja(nodo.value)
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str) and len(nodo.value) == 1:
            return hoja(ord(nodo.value))
        if (isinstance(nodo, ast.UnaryOp) and isinstance(nodo.op, ast.USub)
                and isinstance(nodo.operand, ast.Constant) and isinstance(nodo.operand.value, int)):
            return hoja(-nodo.operand.value)
        if isinstance(nodo, ast.UnaryOp) and isinstance(nodo.op, ast.USub):
            return en(-valor(nodo.operand)).valor_guardado
        if isinstance(nodo, ast.UnaryOp) and isinstance(nodo.op, ast.Invert):
            a = valor(nodo.operand)
            r = en(~a)
            pasos.append(Paso(f"~{a}", [en(a)], r))
            return r.valor_guardado
        if isinstance(nodo, ast.BinOp) and type(nodo.op) in _OPERADORES:
            a, b = valor(nodo.left), valor(nodo.right)
            simbolo = _OPERADORES[type(nodo.op)]
            nota = ""
            if simbolo in ("<<", ">>") and not 0 <= b < operacion.bits:
                raise ValorInvalido(f"desplazar {b} posiciones un {operacion.nombre} de {operacion.bits} bits es "
                                    "comportamiento indefinido en C.")
            patron_a = a % (1 << operacion.bits)
            if simbolo == "&":
                r_val = a & b
            elif simbolo == "|":
                r_val = a | b
            elif simbolo == "^":
                r_val = a ^ b
            elif simbolo == "<<":
                r_val = patron_a << b
                if operacion.con_signo and a < 0:
                    nota = ("desplazar a la izquierda un negativo es comportamiento indefinido en C "
                            "(usá un tipo sin signo).")
                elif operacion.con_signo and a << b > (1 << (operacion.bits - 1)) - 1:
                    nota = (f"{a} << {b} = {a << b} no entra en {operacion.nombre}: el desborde con signo es "
                            "comportamiento indefinido en C (usá un tipo sin signo).")
            else:  # >>: aritmético si tiene signo (lo usual en gcc), lógico si no
                r_val = a >> b if operacion.con_signo else patron_a >> b
                if operacion.con_signo and a < 0:
                    nota = ("desplazar a la derecha un negativo depende de la implementación: gcc copia el bit "
                            "de signo (desplazamiento aritmético).")
            r = en(r_val)
            pasos.append(Paso(f"{a} {simbolo} {b}", [en(a), en(b)], r, nota))
            return r.valor_guardado
        raise ValorInvalido("solo se admiten literales enteros y los operadores &, |, ^, ~, << y >>.")

    final = valor(arbol.body)
    resultado = representar_entero(final, tipo, orden)
    if operacion is not tipo and pasos:
        resultado.explicacion.insert(0, (
            f"Promoción entera: en C, los valores de tipo {tipo.nombre} se convierten a int antes de operar, "
            f"así que cada paso se hace en {operacion.bits} bits; el resultado ({final}) se guarda de vuelta "
            f"en {tipo.nombre}."))
    return resultado, pasos


def es_expresion(texto: str) -> bool:
    return any(op in texto for op in ("&", "|", "^", "~", "<<", ">>"))
