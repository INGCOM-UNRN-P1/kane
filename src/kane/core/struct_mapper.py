"""Mapeo de archivos binarios a layouts de structs C."""

import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from kane.core.models import StructFieldLayout, BinaryRecord, FileInspectionReport, HallazgoBinario


class EspecificacionInvalida(ValueError):
    """La definición del struct no se puede mapear con fidelidad a un layout binario."""


# Cómo se decodifica cada tipo con el módulo `struct`. El tamaño y la alineación no están acá:
# salen de la tabla por ABI de brett (`brett.core.layout.ABIS`), la misma con la que brett mide
# el relleno y bishop dibuja los offsets (Ola 28). Para los enteros, la letra sólo dice si es con
# signo (minúscula) o sin signo (mayúscula): la definitiva sale del tamaño en la ABI (`long` ocupa
# 8 bytes en x86_64 y 4 en Windows o i386).
TYPE_MAP: Dict[str, str] = {
    "char": "c",
    "signed char": "b",
    "unsigned char": "B",
    "bool": "?",
    "short": "h",
    "unsigned short": "H",
    "int": "i",
    "unsigned int": "I",
    "long": "q",
    "unsigned long": "Q",
    "long long": "q",
    "unsigned long long": "Q",
    "float": "f",
    "double": "d",
    "int8_t": "b",
    "uint8_t": "B",
    "int16_t": "h",
    "uint16_t": "H",
    "int32_t": "i",
    "uint32_t": "I",
    "int64_t": "q",
    "uint64_t": "Q",
    "size_t": "Q",
    "ssize_t": "q",
}

_ENTERO_POR_TAMANIO = {1: "b", 2: "h", 4: "i", 8: "q"}


def abis() -> List[str]:
    """Las ABIs que conoce brett (x86_64, x86_64-windows, i386, aarch64, riscv64…)."""
    from brett.core.layout import ABIS

    return list(ABIS)


def validar_abi(abi: str) -> str:
    if abi not in abis():
        raise EspecificacionInvalida(f"ABI desconocida '{abi}'; usá {', '.join(abis())}.")
    return abi


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
    abi: str = "x86_64"

    @property
    def _tamanio_alineacion(self) -> Tuple[int, int]:
        from brett.core.layout import tamanio_alineacion

        return tamanio_alineacion(self.tipo, self.abi)

    @property
    def formato(self) -> str:
        letra = TYPE_MAP[self.tipo]
        if letra.lower() not in "bhiq":
            return letra
        entero = _ENTERO_POR_TAMANIO[self.tamanio_elemento]
        return entero.upper() if letra.isupper() else entero

    @property
    def tamanio_elemento(self) -> int:
        return self._tamanio_alineacion[0]

    @property
    def es_cadena(self) -> bool:
        return self.tipo == "char" and self.cantidad is not None

    @property
    def tamanio(self) -> int:
        return self.tamanio_elemento * (self.cantidad or 1)

    @property
    def alineacion(self) -> int:
        # No siempre coincide con el tamaño: en i386, `double` ocupa 8 bytes y se alinea a 4.
        return self._tamanio_alineacion[1]

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
        raise EspecificacionInvalida("'long double' (80 bits en x86, con relleno según la ABI) no está soportado")
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


def _parsear_campo(item: str, constantes: Dict[str, int], abi: str = "x86_64") -> CampoSpec:
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
    return CampoSpec(nombre=nombre, tipo=tipo, cantidad=cantidad, abi=abi)


def parse_struct_spec(spec_str: str, constantes: Optional[Dict[str, int]] = None, abi: str = "x86_64") -> List[CampoSpec]:
    """Parsea 'int id, char nombre[20], double promedio' en campos con el tamaño y la alineación de
    cada tipo en la ABI pedida (por omisión x86_64 Linux, LP64)."""
    validar_abi(abi)
    campos = [_parsear_campo(item.strip(), constantes or {}, abi) for item in spec_str.split(",") if item.strip()]
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
    """Layout con las reglas de alineación de C: (campo, nombre, offset, tamaño, es_padding).

    Los offsets los calcula brett (`brett.core.layout.disponer`), el dueño del layout de structs:
    así kane lee los registros con los mismos offsets que brett informa."""
    from brett.core.layout import disponer

    por_nombre = {c.nombre: c for c in campos}
    elementos, total = disponer([(c.nombre, c.tamanio, c.alineacion) for c in campos])
    items = [(None if e.es_relleno else por_nombre[e.nombre], e.nombre, e.offset, e.tamanio, e.es_relleno)
             for e in elementos]
    return items, total, any(e.es_relleno for e in elementos)


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
    abi: str = "x86_64",
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
            abi=abi,
            passed=True
        )

    campos = parse_struct_spec(struct_spec, abi=abi)
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

    hallazgos = diagnosticar(data, campos, layout_items, record_size, records)
    return FileInspectionReport(
        file_path=str(file_path),
        file_size_bytes=file_size,
        struct_size_bytes=record_size,
        records_count=rec_count,
        remaining_bytes=remaining,
        records=records,
        has_alignment_padding=has_padding,
        byte_order=endian,
        abi=abi,
        struct_definition=struct_spec,
        passed=(remaining == 0) and not any(h.severidad == "error" for h in hallazgos),
        hallazgos=hallazgos,
    )


def diagnosticar(data: bytes, campos: List[CampoSpec], layout_items, record_size: int,
                 records: List[BinaryRecord]) -> List[HallazgoBinario]:
    """Qué dice el archivo del programa que lo escribió (Ola 18, QoL #548, #554):

    - KANE003: el tamaño no es múltiplo del struct (con relleno) pero sí de la suma de sus campos: se
      escribió campo por campo (`fwrite` de cada campo) y se lee con `fread` del struct, o al revés;
      los registros quedan desalineados.
    - KANE001: el último registro está incompleto (el programa se cortó o escribió de menos): qué
      campos llegaron enteros y cuál quedó truncado.
    - KANE002: el relleno tiene bytes distintos de 0: memoria sin inicializar que `fwrite` copió al
      archivo (inofensiva al leer, pero muestra que el struct no se inicializó).
    - KANE004: un `char[]` sin `'\0'`: se escribió una cadena que llenó el arreglo sin terminador.
    """
    hallazgos: List[HallazgoBinario] = []
    tamanio = len(data)
    empaquetado = sum(c.tamanio for c in campos)
    resto = tamanio % record_size
    if resto and empaquetado != record_size and tamanio % empaquetado == 0:
        hallazgos.append(HallazgoBinario(
            codigo="KANE003", severidad="error",
            mensaje=(f"El archivo tiene {tamanio} B: no es múltiplo del struct ({record_size} B con relleno) pero sí "
                     f"de sus campos sin relleno ({empaquetado} B, {tamanio // empaquetado} registros). Se escribió "
                     "campo por campo y se lee con el struct entero (o al revés): los registros quedan desalineados."),
            sugerencia=("Escribí y leé de la misma forma: fwrite(&r, sizeof(r), 1, f) y fread(&r, sizeof(r), 1, f), "
                        "o campo por campo en los dos lados."),
        ))
    elif resto:
        inicio = tamanio - resto
        completos = [n for c, n, off, tam, pad in layout_items if not pad and off + tam <= resto]
        cortado = next(((n, off, tam) for c, n, off, tam, pad in layout_items if not pad and off < resto < off + tam), None)
        detalle = f"llegaron enteros {', '.join(completos)}" if completos else "no llegó ningún campo entero"
        if cortado:
            detalle += f" y '{cortado[0]}' quedó truncado ({resto - cortado[1]} de {cortado[2]} B)"
        hallazgos.append(HallazgoBinario(
            codigo="KANE001", severidad="error", registro=len(records) + 1, offset=inicio,
            campo=cortado[0] if cortado else None,
            mensaje=f"El último registro está incompleto: tiene {resto} de {record_size} B ({detalle}).",
            sugerencia=("El programa se cortó o escribió de menos: revisá el valor que devuelve fwrite y que el "
                        "archivo se cierre con fclose."),
        ))

    if any(h.codigo == "KANE003" for h in hallazgos):
        return hallazgos  # con los registros corridos, el «relleno» y las cadenas que se leen no son tales
    rellenos = [(off, tam) for c, n, off, tam, pad in layout_items if pad]
    con_basura = [r.index for r in records
                  if any(any(data[r.start_offset + off:r.start_offset + off + tam]) for off, tam in rellenos)]
    if con_basura:
        hallazgos.append(HallazgoBinario(
            codigo="KANE002", severidad="advertencia", registro=con_basura[0],
            offset=records[con_basura[0] - 1].start_offset + next(
                off for off, tam in rellenos
                if any(data[records[con_basura[0] - 1].start_offset + off:records[con_basura[0] - 1].start_offset + off + tam])),
            mensaje=(f"En {len(con_basura)} de {len(records)} registros el relleno entre campos tiene bytes distintos de 0 "
                     "(basura de la memoria que fwrite copió al archivo)."),
            sugerencia="Inicializá el struct antes de completarlo: registro_t r = {0}; o memset(&r, 0, sizeof r);",
        ))

    for c, n, off, tam, pad in layout_items:
        if pad or c is None or not c.es_cadena:
            continue
        sin_fin = [r.index for r in records if 0 not in data[r.start_offset + off:r.start_offset + off + tam]]
        if sin_fin:
            hallazgos.append(HallazgoBinario(
                codigo="KANE004", severidad="advertencia", registro=sin_fin[0], campo=n,
                offset=records[sin_fin[0] - 1].start_offset + off,
                mensaje=(f"'{n}' ({c.nombre_tipo}) no tiene '\\0' en {len(sin_fin)} de {len(records)} registros: la "
                         "cadena llenó el arreglo sin terminador."),
                sugerencia=(f"Copiá como mucho {tam - 1} caracteres y terminá la cadena (strncpy no la termina si llena "
                            f"el arreglo): {n}[{tam - 1}] = '\\0';"),
            ))
    return hallazgos
