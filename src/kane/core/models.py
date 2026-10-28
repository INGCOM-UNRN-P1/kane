"""Modelos de datos para la inspección binaria en KANE."""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class StructFieldLayout(BaseModel):
    name: str
    type_name: str
    offset: int
    size: int
    is_padding: bool = False
    raw_bytes_hex: str = ""
    interpreted_value: Any = None


class BinaryRecord(BaseModel):
    index: int
    start_offset: int
    end_offset: int
    fields: List[StructFieldLayout] = Field(default_factory=list)


class HallazgoBinario(BaseModel):
    """Algo que el archivo binario dice del programa que lo escribió (Ola 18)."""
    codigo: str  # KANE001 registro truncado, KANE002 relleno con basura, KANE003 desalineación, KANE004 cadena sin '\0'
    severidad: str  # "error" o "advertencia"
    mensaje: str
    sugerencia: str
    registro: Optional[int] = None
    campo: Optional[str] = None
    offset: Optional[int] = None


class FileInspectionReport(BaseModel):
    schema_version: str = "1.1.0"
    file_path: str
    file_size_bytes: int
    struct_size_bytes: Optional[int] = None
    records_count: int = 0
    remaining_bytes: int = 0
    records: List[BinaryRecord] = Field(default_factory=list)
    has_alignment_padding: bool = False
    byte_order: str = "little"
    struct_definition: Optional[str] = None
    passed: bool = True
    hallazgos: List[HallazgoBinario] = Field(default_factory=list)
