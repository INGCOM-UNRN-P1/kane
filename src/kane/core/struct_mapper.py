"""Mapeo de archivos binarios a layouts de structs C."""

import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from kane.core.models import StructFieldLayout, BinaryRecord, FileInspectionReport


class EspecificacionInvalida(ValueError):
    """La definición del struct no se puede mapear con fidelidad a un layout binario."""


# Formato de `struct`, tamaño y alineación (ABI LP64: x86-64 Linux, donde `long`
# ocupa 8 bytes). La alineación de un escalar coincide con su tamaño. Una única
# tabla evita que el tamaño (layout) y el formato (decodificación) discrepen,
# que es lo que pasaba cuando el tamaño venía de otra fuente.
TYPE_MAP: Dict[str, Tuple[str, int]] = {
    "char": ("c", 1),
    "signed char": ("b", 1),
    "unsigned char": ("B", 1),
    "bool": ("?", 1),
    "short": ("h", 2),
    "unsigned short": ("H", 2),
    "int": ("i", 4),
    "unsigned int": ("I", 4),
    "long": ("q", 8),
    "unsigned long": ("Q", 8),
    "long long": ("q", 8),
    "unsigned long long": ("Q", 8),
    "float": ("f", 4),
    "double": ("d", 8),
    "int8_t": ("b", 1),
    "uint8_t": ("B", 1),
    "int16_t": ("h", 2),
    "uint16_t": ("H", 2),
    "int32_t": ("i", 4),
    "uint32_t": ("I", 4),
    "int64_t": ("q", 8),
    "uint64_t": ("Q", 8),
    "size_t": ("Q", 8),
    "ssize_t": ("q", 8),
}

_ALIAS_UNA_PALABRA = {"_Bool": "bool"}
_ENTEROS = {
    (): "int",
    ("int",): "int",
    ("short",): "short",
    ("short", "int"): "short",
    ("long",): "long",
    ("long", "int"): "long",
    ("long", "long"): "long long",
    ("long", "long", "int"): "long long",
}


@dataclass(frozen=True)
class CampoSpec:
    nombre: str
    tipo: str
    cantidad: Optional[int]  # None: escalar; N: arreglo de N elementos

    @property
    def formato(self) -> str:
        return TYPE_MAP[self.tipo][0]

    @property
    def tamanio_elemento(self) -> int:
        return TYPE_MAP[self.tipo][1]

    @property
    def es_cadena(self) -> bool:
        return self.tipo == "char" and self.cantidad is not None

    @property
    def tamanio(self) -> int:
        return self.tamanio_elemento * (self.cantidad or 1)

    @property
    def alineacion(self) -> int:
        return self.tamanio_elemento

    @property
    def nombre_tipo(self) -> str:
        return f"{self.tipo}[{self.cantidad}]" if self.cantidad is not None else self.tipo


def resolver_tipo(texto: str) -> str:
    """Normaliza un tipo C escrito por el usuario al nombre canónico de TYPE_MAP."""
    palabras = [w for w in texto.split() if w not in ("const", "volatile")]
    if not palabras:
        raise EspecificacionInvalida(f"falta el tipo en '{texto}'")
    if any(w in ("struct", "union") for w in palabras):
        raise EspecificacionInvalida(
            f"'{texto}': los struct/union anidados no están soportados; aplaná el layout con los campos "
            "escalares que ocupan sus bytes."
        )
    if palabras[0] == "enum":
        return "int"
    if len(palabras) == 1 and palabras[0] in TYPE_MAP:
        return palabras[0]
    if len(palabras) == 1 and palabras[0] in _ALIAS_UNA_PALABRA:
        return _ALIAS_UNA_PALABRA[palabras[0]]

    sin_signo = "unsigned" in palabras
    con_signo = "signed" in palabras
    resto = tuple(w for w in palabras if w not in ("unsigned", "signed"))
    if resto == ("char",):
        canon = "unsigned char" if sin_signo else ("signed char" if con_signo else "char")
    elif resto == ("long", "double"):
        raise EspecificacionInvalida("'long double' (80 bits en x86-64) no está soportado")
    elif resto in (("float",), ("double",)) and not (sin_signo or con_signo):
        canon = resto[0]
    elif resto in _ENTEROS:
        base = _ENTEROS[resto]
        canon = f"unsigned {base}" if sin_signo else base
    else:
        raise EspecificacionInvalida(
            f"tipo desconocido '{texto}'. Soportados: {', '.join(sorted(TYPE_MAP))}."
        )
    if canon not in TYPE_MAP:
        raise EspecificacionInvalida(f"tipo desconocido '{texto}'")
    return canon


_DECLARACION = re.compile(r"^(?P<cabeza>[^\[\]]*?)(?P<dims>(?:\s*\[[^\]]*\])*)\s*$")


def _parsear_campo(item: str, constantes: Dict[str, int]) -> CampoSpec:
    m = _DECLARACION.match(item)
    if not m or "*" in item or "(" in item or ":" in item:
        motivo = (
            "los punteros no se pueden leer de un archivo" if "*" in item
            else "los bit-fields y punteros a función no están soportados" if (":" in item or "(" in item)
            else "no es una declaración de campo"
        )
        raise EspecificacionInvalida(f"campo '{item}': {motivo}.")
    palabras = m.group("cabeza").split()
    if len(palabras) < 2:
        raise EspecificacionInvalida(f"campo '{item}': se esperaba '<tipo> <nombre>'.")
    nombre = palabras[-1]
    if not re.fullmatch(r"[A-Za-z_]\w*", nombre):
        raise EspecificacionInvalida(f"campo '{item}': '{nombre}' no es un identificador válido.")
    tipo = resolver_tipo(" ".join(palabras[:-1]))

    dims = re.findall(r"\[([^\]]*)\]", m.group("dims"))
    if len(dims) > 1:
        raise EspecificacionInvalida(f"campo '{item}': los arreglos multidimensionales no están soportados.")
    cantidad: Optional[int] = None
    if dims:
        crudo = dims[0].strip()
        if crudo.isdigit():
            cantidad = int(crudo)
        elif crudo in constantes:
            cantidad = constantes[crudo]
        else:
            raise EspecificacionInvalida(
                f"campo '{item}': la dimensión '{crudo}' no es un número entero literal "
                "(kane no expande macros que no estén definidas con #define en la cabecera)."
            )
        if cantidad <= 0:
            raise EspecificacionInvalida(f"campo '{item}': la dimensión debe ser mayor que cero.")
    return CampoSpec(nombre=nombre, tipo=tipo, cantidad=cantidad)


def parse_struct_spec(spec_str: str, constantes: Optional[Dict[str, int]] = None) -> List[CampoSpec]:
    """Parsea 'int id, char nombre[20], double promedio' en campos con tipo y tamaño reales."""
    campos = [_parsear_campo(item.strip(), constantes or {}) for item in spec_str.split(",") if item.strip()]
    if not campos:
        raise EspecificacionInvalida("la especificación del struct no contiene ningún campo.")
    repetidos = {c.nombre for c in campos if [x.nombre for x in campos].count(c.nombre) > 1}
    if repetidos:
        raise EspecificacionInvalida(f"nombres de campo repetidos: {', '.join(sorted(repetidos))}.")
    return campos


def _sin_comentarios(texto: str) -> str:
    """Quita comentarios respetando los literales de cadena y de carácter."""
    salida: List[str] = []
    i, n = 0, len(texto)
    while i < n:
        c = texto[i]
        if c in "\"'":
            j = i + 1
            while j < n and texto[j] != c:
                j += 2 if texto[j] == "\\" else 1
            salida.append(texto[i:j + 1])
            i = j + 1
        elif texto.startswith("//", i):
            j = texto.find("\n", i)
            i = n if j == -1 else j
        elif texto.startswith("/*", i):
            j = texto.find("*/", i + 2)
            i = n if j == -1 else j + 2
            salida.append(" ")
        else:
            salida.append(c)
            i += 1
    return "".join(salida)


@dataclass(frozen=True)
class StructCabecera:
    spec: Optional[str]  # None si el struct no se puede mapear
    error: Optional[str] = None


_STRUCT_TIPO = re.compile(r"\b(?:typedef\s+)?struct\s*(?P<etiqueta>[A-Za-z_]\w*)?\s*\{")
_DEFINE_ENTERO = re.compile(r"^[ \t]*#[ \t]*define[ \t]+([A-Za-z_]\w*)[ \t]+(\d+)[ \t]*$", re.M)


def _cuerpo_balanceado(texto: str, abre: int) -> Tuple[str, int]:
    nivel, i = 0, abre
    while i < len(texto):
        if texto[i] == "{":
            nivel += 1
        elif texto[i] == "}":
            nivel -= 1
            if nivel == 0:
                return texto[abre + 1:i], i + 1
        i += 1
    raise EspecificacionInvalida("llave sin cerrar en la definición del struct.")


def structs_de_cabecera(header: Path) -> Dict[str, StructCabecera]:
    """Devuelve {nombre: definición} para cada struct definido en la cabecera.

    El nombre es el del `typedef` si existe y la etiqueta (`struct Etiqueta`) en
    caso contrario; ambos se aceptan al pedir un struct por nombre.
    """
    limpio = _sin_comentarios(header.read_text(encoding="utf-8", errors="replace"))
    constantes = {k: int(v) for k, v in _DEFINE_ENTERO.findall(limpio)}
    sin_preprocesador = "\n".join(
        "" if linea.lstrip().startswith("#") else linea for linea in limpio.splitlines()
    )

    encontrados: Dict[str, StructCabecera] = {}
    for m in _STRUCT_TIPO.finditer(sin_preprocesador):
        cuerpo, fin = _cuerpo_balanceado(sin_preprocesador, m.end() - 1)
        alias = re.match(r"\s*([A-Za-z_]\w*)\s*;", sin_preprocesador[fin:])
        nombre_typedef = alias.group(1) if alias and m.group(0).lstrip().startswith("typedef") else None
        etiqueta = m.group("etiqueta")

        nombres = [n for n in (nombre_typedef, etiqueta) if n]
        # Un struct inválido se registra con su error: no impide usar los demás de
        # la misma cabecera y el mensaje nombra al que lo causa.
        try:
            spec = ", ".join(_miembros_de_cuerpo(cuerpo))
            parse_struct_spec(spec, constantes)
        except EspecificacionInvalida as exc:
            for nombre in nombres:
                encontrados[nombre] = StructCabecera(spec=None, error=str(exc))
            continue
        # Las dimensiones simbólicas se resuelven con los #define de la cabecera para
        # que la especificación resultante sea autocontenida.
        spec_resuelta = re.sub(
            r"\[\s*([A-Za-z_]\w*)\s*\]",
            lambda mm: f"[{constantes[mm.group(1)]}]" if mm.group(1) in constantes else mm.group(0),
            spec,
        )
        for nombre in nombres:
            encontrados[nombre] = StructCabecera(spec=spec_resuelta)
    return encontrados


def _miembros_de_cuerpo(cuerpo: str) -> List[str]:
    miembros: List[str] = []
    for sentencia in cuerpo.split(";"):
        sentencia = " ".join(sentencia.split())
        if not sentencia:
            continue
        if "{" in sentencia or "}" in sentencia:
            raise EspecificacionInvalida("contiene un struct/union anidado, que no está soportado.")
        declaradores = [d.strip() for d in sentencia.split(",")]
        miembros.append(declaradores[0])
        if len(declaradores) > 1:
            # `int a, b;` comparte el tipo del primer declarador.
            palabras = declaradores[0].split()
            tipo_base = " ".join(palabras[:-1]) if len(palabras) > 1 else ""
            miembros.extend(f"{tipo_base} {d}" for d in declaradores[1:])
    return miembros


def struct_de_cabecera(header: Path, nombre: Optional[str] = None) -> Tuple[str, str]:
    """Obtiene (nombre, spec) del struct pedido; sin nombre exige que haya uno solo."""
    estructuras = structs_de_cabecera(header)
    if not estructuras:
        raise EspecificacionInvalida(f"{header.name}: no se encontró ninguna definición de struct.")
    if nombre is None:
        # `typedef struct P {..} P_t;` figura bajo dos nombres para una misma definición.
        distintos = {(e.spec, e.error) for e in estructuras.values()}
        if len(distintos) > 1:
            raise EspecificacionInvalida(
                f"{header.name} define varios structs ({', '.join(sorted(estructuras))}); indicá cuál con --name."
            )
        nombre = sorted(estructuras)[0]
    if nombre not in estructuras:
        raise EspecificacionInvalida(
            f"{header.name}: no hay un struct llamado '{nombre}'. Disponibles: {', '.join(sorted(estructuras))}."
        )
    definicion = estructuras[nombre]
    if definicion.spec is None:
        raise EspecificacionInvalida(f"struct '{nombre}': {definicion.error}")
    return nombre, definicion.spec


def _calcular_layout(campos: List[CampoSpec]) -> Tuple[List[Tuple[Optional[CampoSpec], str, int, int, bool]], int, bool]:
    """Layout con las reglas de alineación de C: (campo, nombre, offset, tamaño, es_padding)."""
    items: List[Tuple[Optional[CampoSpec], str, int, int, bool]] = []
    offset = 0
    max_align = 1
    hay_padding = False
    for campo in campos:
        alinea = campo.alineacion
        max_align = max(max_align, alinea)
        if offset % alinea != 0:
            pad = alinea - (offset % alinea)
            items.append((None, f"_pad_{offset}", offset, pad, True))
            offset += pad
            hay_padding = True
        items.append((campo, campo.nombre, offset, campo.tamanio, False))
        offset += campo.tamanio
    if offset % max_align != 0:
        pad = max_align - (offset % max_align)
        items.append((None, f"_tail_pad_{offset}", offset, pad, True))
        offset += pad
        hay_padding = True
    return items, max(offset, 1), hay_padding


def _interpretar(campo: CampoSpec, chunk: bytes, prefijo: str):
    if campo.es_cadena:
        return chunk.split(b"\x00", 1)[0].decode("utf-8", errors="replace")
    if campo.cantidad is not None:
        return [_desempaquetar(campo, chunk[i:i + campo.tamanio_elemento], prefijo)
                for i in range(0, campo.tamanio, campo.tamanio_elemento)]
    return _desempaquetar(campo, chunk, prefijo)


def _desempaquetar(campo: CampoSpec, chunk: bytes, prefijo: str):
    valor = struct.unpack(f"{prefijo}{campo.formato}", chunk)[0]
    if isinstance(valor, bytes):
        # `struct.unpack("<c", ...)` devuelve bytes (b'A'), que no es serializable
        # a JSON y rompía `--json`, la única salida que un pipeline puede consumir.
        return valor.decode("utf-8", errors="replace")
    return valor


ORDENES_DE_BYTES = ("little", "big")


def inspect_binary_file(
    file_path: Path,
    struct_spec: Optional[str] = None,
    endian: str = "little",
) -> FileInspectionReport:
    """Lee un archivo binario y mapea sus registros y bytes considerando alineación y padding de C.

    `endian` es el orden de bytes con que se interpretan los campos multibyte;
    kane no lo detecta: lo decide quien conoce la máquina que escribió el archivo.
    """
    if endian not in ORDENES_DE_BYTES:
        raise EspecificacionInvalida(f"orden de bytes '{endian}' inválido; usá {' o '.join(ORDENES_DE_BYTES)}.")
    prefijo = "<" if endian == "little" else ">"

    data = file_path.read_bytes()
    file_size = len(data)

    if not struct_spec:
        return FileInspectionReport(
            file_path=str(file_path),
            file_size_bytes=file_size,
            struct_size_bytes=None,
            records_count=0,
            remaining_bytes=file_size,
            records=[],
            byte_order=endian,
            passed=True
        )

    campos = parse_struct_spec(struct_spec)
    layout_items, record_size, has_padding = _calcular_layout(campos)

    records: List[BinaryRecord] = []
    rec_count = file_size // record_size
    remaining = file_size % record_size

    for rec_idx in range(rec_count):
        offset_start = rec_idx * record_size
        rec_data = data[offset_start:offset_start + record_size]

        field_layouts: List[StructFieldLayout] = []
        for campo, f_name, f_rel_offset, f_size, is_pad in layout_items:
            chunk = rec_data[f_rel_offset:f_rel_offset + f_size]
            hex_val = chunk.hex(" ")
            interp_val = None
            if campo is not None:
                try:
                    interp_val = _interpretar(campo, chunk, prefijo)
                except struct.error:
                    interp_val = hex_val

            field_layouts.append(StructFieldLayout(
                name=f_name,
                type_name=campo.nombre_tipo if campo is not None else "padding",
                offset=offset_start + f_rel_offset,
                size=f_size,
                is_padding=is_pad,
                raw_bytes_hex=hex_val,
                interpreted_value=interp_val
            ))

        records.append(BinaryRecord(
            index=rec_idx + 1,
            start_offset=offset_start,
            end_offset=offset_start + record_size,
            fields=field_layouts
        ))

    return FileInspectionReport(
        file_path=str(file_path),
        file_size_bytes=file_size,
        struct_size_bytes=record_size,
        records_count=rec_count,
        remaining_bytes=remaining,
        records=records,
        has_alignment_padding=has_padding,
        byte_order=endian,
        struct_definition=struct_spec,
        passed=(remaining == 0)
    )
