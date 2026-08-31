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


def generar_seccion_markdown(report: FileInspectionReport) -> str:
    """Genera sección de inspección binaria y struct mapping para Dredd."""
    lines = ["## Inspección de Archivos Binarios y Structs (Kane)\n"]
    lines.append(f"- **Archivo analizado:** `{Path(report.file_path).name}`")
    lines.append(f"- **Tamaño del archivo:** {report.file_size_bytes} bytes")
    lines.append(f"- **Registros parseados:** {len(report.records)}")
    if report.remaining_bytes > 0:
        lines.append(f"- **Bytes truncados/residuales:** {report.remaining_bytes} B\n")
        lines.append("> [!WARNING]\n> **Bytes Huérfanos:** El archivo binario contiene bytes finales que no completan un struct completo.\n")
    else:
        lines.append("\n> [!TIP]\n> **Estructura Binaria Válida:** Todos los registros corresponden con el tamaño de struct esperado.\n")

    if report.records:
        lines.append("| Reg # | Campo | Tipo | Offset | Hex Bytes | Valor Interpretado |")
        lines.append("| :---: | :--- | :---: | :---: | :--- | :--- |")
        for rec in report.records:
            for idx, fld in enumerate(rec.fields):
                reg_str = str(rec.index) if idx == 0 else ""
                lines.append(f"| {reg_str} | `{fld.name}` | {fld.type_name} | `0x{fld.offset:04X}` | `{fld.raw_bytes_hex}` | `{fld.interpreted_value}` |")
        lines.append("")
    return "\n".join(lines)


@app.command("inspect")
@app.command("check")
def inspect(
    file_path: Path = typer.Argument(..., help="Archivo binario (.bin, .dat) a inspeccionar", exists=True),
    struct_spec: Optional[str] = typer.Option(None, "--struct", "-s", help="Especificación de struct: 'int id, char nombre[20], float nota'"),
    json_output: bool = typer.Option(False, "--json", help="Emitir salida en formato JSON estructurado"),
    output_md: Optional[Path] = typer.Option(None, "--md", "--output-md", help="Generar sección de reporte en formato Markdown para fusión en Dredd."),
):
    """Inspecciona y desglosa el contenido de un archivo binario mapeándolo a un struct C."""
    report = inspect_binary_file(file_path, struct_spec)

    if output_md:
        md_text = generar_seccion_markdown(report)
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(md_text, encoding="utf-8")
        console.print(f"[bold green]✓ Sección Markdown generada en:[/bold green] {output_md}")
        raise typer.Exit(code=0)

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


@app.command("report")
def report_cmd(
    file_path: Path = typer.Argument(..., help="Archivo binario (.bin, .dat) a inspeccionar", exists=True),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Ruta de destino del archivo Markdown."),
    struct_spec: Optional[str] = typer.Option(None, "--struct", "-s", help="Especificación del struct C."),
):
    """Genera directamente la sección de reporte Markdown de KANE para Dredd."""
    report = inspect_binary_file(file_path, struct_spec)
    md_content = generar_seccion_markdown(report)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(md_content, encoding="utf-8")
        console.print(f"[bold green]✓ Reporte Markdown generado en:[/bold green] {output}")
    else:
        print(md_content)


@app.command()
def version():
    """Muestra la versión de KANE."""
    from kane import __version__
    console.print(f"[bold cyan]KANE[/bold cyan] versión [green]{__version__}[/green]")


if __name__ == "__main__":
    app()
