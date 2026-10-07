"""Comparación de dos archivos binarios del mismo struct, registro por registro y campo por campo
(QoL #554): qué cambió entre dos grabaciones (antes y después de una modificación, la salida del
estudiante contra la esperada)."""

from __future__ import annotations

from typing import Any, Dict, List

from kane.core.models import FileInspectionReport


def comparar_reportes(a: FileInspectionReport, b: FileInspectionReport) -> Dict[str, Any]:
    """Las diferencias entre dos inspecciones hechas con el mismo struct. El relleno se ignora: su
    contenido no está definido y difiere entre dos grabaciones correctas."""
    diferencias: List[Dict[str, Any]] = []
    for ra, rb in zip(a.records, b.records, strict=False):
        for fa, fb in zip(ra.fields, rb.fields, strict=False):
            if fa.is_padding or fa.raw_bytes_hex == fb.raw_bytes_hex:
                continue
            diferencias.append({
                "registro": ra.index,
                "campo": fa.name,
                "tipo": fa.type_name,
                "offset": fa.offset,
                "valor_a": fa.interpreted_value,
                "valor_b": fb.interpreted_value,
            })
    return {
        "schema_version": "1.0.0",
        "archivo_a": a.file_path,
        "archivo_b": b.file_path,
        "struct_size_bytes": a.struct_size_bytes,
        "registros_a": a.records_count,
        "registros_b": b.records_count,
        "registros_comparados": min(a.records_count, b.records_count),
        "diferencias": diferencias,
        "iguales": not diferencias and a.records_count == b.records_count and a.remaining_bytes == b.remaining_bytes,
    }
