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


class FileInspectionReport(BaseModel):
    file_path: str
    file_size_bytes: int
    struct_size_bytes: Optional[int] = None
    records_count: int = 0
    remaining_bytes: int = 0
    records: List[BinaryRecord] = Field(default_factory=list)
    has_alignment_padding: bool = False
    passed: bool = True
