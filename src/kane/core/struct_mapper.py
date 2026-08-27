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


def inspect_binary_file(
    file_path: Path,
    struct_spec: Optional[str] = None
) -> FileInspectionReport:
    """Lee un archivo binario y mapea sus registros y bytes."""
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
    record_size = sum(f[2] for f in field_specs)
    if record_size == 0:
        record_size = 1

    records: List[BinaryRecord] = []
    rec_count = file_size // record_size
    remaining = file_size % record_size

    for rec_idx in range(rec_count):
        offset_start = rec_idx * record_size
        rec_data = data[offset_start:offset_start + record_size]

        field_layouts: List[StructFieldLayout] = []
        cur_offset = 0

        for f_name, f_type, f_size in field_specs:
            chunk = rec_data[cur_offset:cur_offset + f_size]
            hex_val = chunk.hex(" ")
            interp_val = None

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
                offset=offset_start + cur_offset,
                size=f_size,
                is_padding=False,
                raw_bytes_hex=hex_val,
                interpreted_value=interp_val
            ))
            cur_offset += f_size

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
        has_alignment_padding=False,
        passed=(remaining == 0)
    )
