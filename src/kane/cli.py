"""CLI principal de KANE."""

import json
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from kane.core.models import FileInspectionReport
from kane.core.struct_mapper import inspect_binary_file

app = typer.Typer(
    name="kane",
    help="Simulador y depurador visual de I/O de bajo nivel y archivos binarios en C",
    add_completion=True
)
console = Console()


@app.command()
def inspect(
    file_path: Path = typer.Argument(..., help="Archivo binario (.bin, .dat) a inspeccionar", exists=True),
    struct_spec: Optional[str] = typer.Option(None, "--struct", "-s", help="Especificación de struct: 'int id, char nombre[20], float nota'"),
    json_output: bool = typer.Option(False, "--json", help="Emitir salida en formato JSON estructurado")
):
    """Inspecciona y desglosa el contenido de un archivo binario mapeándolo a un struct C."""
    report = inspect_binary_file(file_path, struct_spec)

    if json_output:
        print(json.dumps(report.model_dump(), indent=2, ensure_ascii=False))
        return

    if not struct_spec:
        # Volcado hex estándar
        raw = file_path.read_bytes()
        console.print(Panel(
            f"[bold cyan]Archivo:[/bold cyan] {file_path.name}\n"
            f"[bold cyan]Tamaño:[/bold cyan] {report.file_size_bytes} bytes\n"
            f"[bold cyan]Hex Preview:[/bold cyan] {raw[:64].hex(' ')}...",
            title="[bold green]KANE Hex Dump[/bold green]"
        ))
        return

    table = Table(title=f"Inspección de Registros Binarios ({file_path.name})", show_header=True, header_style="bold magenta")
    table.add_column("Reg #", style="cyan", width=6)
    table.add_column("Offset", style="dim", width=10)
    table.add_column("Campo", style="yellow")
    table.add_column("Tipo", style="blue")
    table.add_column("Hex Bytes", style="dim")
    table.add_column("Valor Interpretado", style="bold green")

    for rec in report.records:
        for idx, fld in enumerate(rec.fields):
            reg_num = str(rec.index) if idx == 0 else ""
            table.add_row(
                reg_num,
                f"0x{fld.offset:04X} ({fld.offset})",
                fld.name,
                fld.type_name,
                fld.raw_bytes_hex,
                str(fld.interpreted_value)
            )

    console.print(table)
    if report.remaining_bytes > 0:
        console.print(f"\n[bold yellow]⚠️ Advertencia: Quedan {report.remaining_bytes} bytes truncados al final del archivo.[/bold yellow]")


@app.command()
def version():
    """Muestra la versión de KANE."""
    from kane import __version__
    console.print(f"[bold cyan]KANE[/bold cyan] versión [green]{__version__}[/green]")


if __name__ == "__main__":
    app()
