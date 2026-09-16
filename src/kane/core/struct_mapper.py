"""Mapeo de archivos binarios a layouts de structs C."""

import struct
from pathlib import Path
from typing import List, Tuple, Optional
from kane.core.models import StructFieldLayout, BinaryRecord, FileInspectionReport


# Tipos básicos de C con sus tamaños y formatos de struct en Python
TYPE_MAP = {
    "char": ("c", 1),
    "int8_t": ("b", 1),
    "uint8_t": ("B", 1),
    "short": ("h", 2),
    "int16_t": ("h", 2),
    "uint16_t": ("H", 2),
    "int": ("i", 4),
    "int32_t": ("i", 4),
    "uint32_t": ("I", 4),
    "long": ("q", 8),
    "int64_t": ("q", 8),
    "uint64_t": ("Q", 8),
    "float": ("f", 4),
    "double": ("d", 8),
}


def parse_simple_struct_spec(spec_str: str) -> List[Tuple[str, str, int]]:
    """Parsea una especificación simple como 'int id, char nombre[20], double promedio'."""
    fields = []
    for item in spec_str.split(","):
        item = item.strip()
        if not item:
            continue
        parts = item.split()
        if len(parts) >= 2:
            type_name = parts[0]
            field_name = parts[1]
            if "[" in field_name:
                base_name, size_part = field_name.split("[", 1)
                size_val = int(size_part.replace("]", "").strip())
                fields.append((base_name, f"char[{size_val}]", size_val))
            else:
                fmt_info = TYPE_MAP.get(type_name, ("i", 4))
                fields.append((field_name, type_name, fmt_info[1]))
    return fields


def _obtener_tamanio_alineacion_brett(tipo: str) -> Tuple[int, int]:
    """Obtiene tamaño y alineación consumiendo el catálogo canónico de Brett."""
    try:
        from brett.core.padding import _obtener_tamanio_alineacion
        return _obtener_tamanio_alineacion(tipo)
    except ImportError:
        import sys
        sibling = Path(__file__).resolve().parents[4] / "brett" / "src"
        if sibling.is_dir() and str(sibling) not in sys.path:
            sys.path.insert(0, str(sibling))
        try:
            from brett.core.padding import _obtener_tamanio_alineacion
            return _obtener_tamanio_alineacion(tipo)
        except ImportError:
            t_clean = tipo.strip()
            if "*" in t_clean:
                return (8, 8)
            mapping = {
                "char": (1, 1), "bool": (1, 1), "int8_t": (1, 1), "uint8_t": (1, 1),
                "short": (2, 2), "int16_t": (2, 2), "uint16_t": (2, 2),
                "int": (4, 4), "float": (4, 4), "int32_t": (4, 4), "uint32_t": (4, 4),
                "size_t": (8, 8), "long": (8, 8), "double": (8, 8),
                "int64_t": (8, 8), "uint64_t": (8, 8),
            }
            for k, v in mapping.items():
                if k in t_clean:
                    return v
            return (4, 4)


def inspect_binary_file(
    file_path: Path,
    struct_spec: Optional[str] = None
) -> FileInspectionReport:
    """Lee un archivo binario y mapea sus registros y bytes considerando alineación y padding de C."""
    data = file_path.read_bytes()
    file_size = len(data)

    if not struct_spec:
        # Modo hex-dump simple si no hay struct
        return FileInspectionReport(
            file_path=str(file_path),
            file_size_bytes=file_size,
            struct_size_bytes=None,
            records_count=0,
            remaining_bytes=file_size,
            records=[],
            passed=True
        )

    field_specs = parse_simple_struct_spec(struct_spec)

    # Calcular layout con alineación y padding consumiendo brett
    layout_items: List[Tuple[str, str, int, int, bool]] = []
    cur_rel_offset = 0
    max_align = 1
    has_padding = False

    for f_name, f_type, f_size in field_specs:
        if f_type.startswith("char["):
            tam = f_size
            align = 1
        else:
            tam_brett, align = _obtener_tamanio_alineacion_brett(f_type)
            tam = f_size or tam_brett

        if align > max_align:
            max_align = align

        if cur_rel_offset % align != 0:
            pad_bytes = align - (cur_rel_offset % align)
            layout_items.append((f"_pad_{cur_rel_offset}", "padding", cur_rel_offset, pad_bytes, True))
            cur_rel_offset += pad_bytes
            has_padding = True

        layout_items.append((f_name, f_type, cur_rel_offset, tam, False))
        cur_rel_offset += tam

    if max_align > 0 and cur_rel_offset % max_align != 0:
        tail_pad = max_align - (cur_rel_offset % max_align)
        layout_items.append((f"_tail_pad_{cur_rel_offset}", "padding", cur_rel_offset, tail_pad, True))
        cur_rel_offset += tail_pad
        has_padding = True

    record_size = max(cur_rel_offset, 1)

    records: List[BinaryRecord] = []
    rec_count = file_size // record_size
    remaining = file_size % record_size

    for rec_idx in range(rec_count):
        offset_start = rec_idx * record_size
        rec_data = data[offset_start:offset_start + record_size]

        field_layouts: List[StructFieldLayout] = []

        for f_name, f_type, f_rel_offset, f_size, is_pad in layout_items:
            chunk = rec_data[f_rel_offset:f_rel_offset + f_size]
            hex_val = chunk.hex(" ")
            interp_val = None

            if not is_pad:
                try:
                    if f_type.startswith("char["):
                        interp_val = chunk.split(b"\x00", 1)[0].decode("utf-8", errors="replace")
                    elif f_type in TYPE_MAP:
                        fmt_char = TYPE_MAP[f_type][0]
                        interp_val = struct.unpack(f"<{fmt_char}", chunk)[0]
                except Exception:
                    interp_val = hex_val

            field_layouts.append(StructFieldLayout(
                name=f_name,
                type_name=f_type,
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
        passed=(remaining == 0)
    )
