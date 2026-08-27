"""Plugin de KANE para el microkernel RIPLEY."""

from pathlib import Path
from typing import Dict, Any
from kane.core.struct_mapper import inspect_binary_file


class KanePlugin:
    """Plugin de inspección de archivos binarios para Ripley."""

    name = "binary_io"
    description = "Inspección de archivos binarios, offsets y mapeo a structs C"

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        source_dir = Path(context.get("source_dir", "."))
        bin_files = list(source_dir.glob("*.bin")) + list(source_dir.glob("*.dat"))

        inspected = []
        for b in bin_files:
            report = inspect_binary_file(b)
            inspected.append({
                "file": b.name,
                "size_bytes": report.file_size_bytes
            })

        return {
            "passed": True,
            "binary_files_count": len(bin_files),
            "files": inspected
        }
