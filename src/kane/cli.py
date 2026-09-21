"""CLI principal de KANE."""

import json
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from kane.core.models import FileInspectionReport
from kane.core.struct_mapper import (
    EspecificacionInvalida,
    inspect_binary_file,
    struct_de_cabecera,
)

app = typer.Typer(
    name="kane",
    help="Simulador y depurador visual de I/O de bajo nivel y archivos binarios en C",
    add_completion=True
)
console = Console()
err_console = Console(stderr=True)


def _version_callback(value: bool) -> None:
    if value:
        from kane import __version__
        console.print(f"[bold cyan]KANE[/bold cyan] versión [green]{__version__}[/green]")
        raise typer.Exit(code=0)


@app.callback()
def main_callback(
    version: Optional[bool] = typer.Option(
        None, "--version", "-v", help="Muestra la versión de KANE.",
        callback=_version_callback, is_eager=True,
    ),
) -> None:
    pass


def generar_seccion_markdown(report: FileInspectionReport) -> str:
    """Genera sección de inspección binaria y struct mapping para Dredd."""
    lines = [
        "<!-- dredd-section: kane v1.0.0 -->\n",
        "## Inspección de Archivos Binarios y Structs (Kane)\n",
    ]
    lines.append(f"- **Archivo analizado:** `{Path(report.file_path).name}`")
    lines.append(f"- **Tamaño del archivo:** {report.file_size_bytes} bytes")
    lines.append(f"- **Registros parseados:** {len(report.records)}")
    if report.struct_definition:
        lines.append(f"- **Struct:** `{report.struct_definition}`")
        lines.append(f"- **Orden de bytes:** {report.byte_order}-endian")
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
                name_limpio = fld.name.replace("|", "&#124;")
                val_limpio = str(fld.interpreted_value).replace("|", "&#124;")
                lines.append(f"| {reg_str} | `{name_limpio}` | {fld.type_name} | `0x{fld.offset:04X}` | `{fld.raw_bytes_hex}` | `{val_limpio}` |")
        lines.append("")
    return "\n".join(lines)


def _codigo_salida(report: FileInspectionReport) -> int:
    """0 si el archivo se parsea completo (`report.passed`); 1 si sobran bytes que no completan un registro."""
    return 0 if report.passed else 1


def _inspeccionar(
    file_path: Path,
    struct_spec: Optional[str],
    header: Optional[Path],
    struct_name: Optional[str],
    endian: str,
) -> FileInspectionReport:
    """Resuelve el struct (spec inline o cabecera .h) e inspecciona; los errores de uso salen con código 2."""
    try:
        if struct_spec and header:
            raise EspecificacionInvalida("usá --struct o --header, no ambos.")
        if struct_name and not header:
            raise EspecificacionInvalida("--name solo tiene sentido junto con --header.")
        if header:
            nombre, struct_spec = struct_de_cabecera(header, struct_name)
            err_console.print(f"[dim]Struct '{nombre}' leído de {header.name}: {struct_spec}[/dim]")
        return inspect_binary_file(file_path, struct_spec, endian=endian)
    except EspecificacionInvalida as exc:
        err_console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=2)


@app.command("inspect")
@app.command("check")
def inspect(
    file_path: Path = typer.Argument(..., help="Archivo binario (.bin, .dat) a inspeccionar", exists=True),
    struct_spec: Optional[str] = typer.Option(None, "--struct", "-s", help="Especificación de struct: 'int id, char nombre[20], float nota'"),
    json_output: bool = typer.Option(False, "--json", help="Emitir salida en formato JSON estructurado"),
    output_md: Optional[Path] = typer.Option(None, "--md", "--output-md", help="Generar sección de reporte en formato Markdown para fusión en Dredd."),
    header: Optional[Path] = typer.Option(None, "--header", "-H", help="Cabecera .h de la que se lee la definición del struct", exists=True, dir_okay=False),
    struct_name: Optional[str] = typer.Option(None, "--name", "-n", help="Nombre del struct dentro de --header (obligatorio si define varios)"),
    endian: str = typer.Option("little", "--endian", "-e", help="Orden de bytes con que se interpretan los campos multibyte: little o big (no se detecta)"),
):
    """Inspecciona y desglosa el contenido de un archivo binario mapeándolo a un struct C."""
    report = _inspeccionar(file_path, struct_spec, header, struct_name, endian)
    struct_spec = report.struct_definition

    if output_md:
        md_text = generar_seccion_markdown(report)
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(md_text, encoding="utf-8")
        console.print(f"[bold green]✓ Sección Markdown generada en:[/bold green] {output_md}")
        raise typer.Exit(code=_codigo_salida(report))

    if json_output:
        print(json.dumps(report.model_dump(), indent=2, ensure_ascii=False))
        raise typer.Exit(code=_codigo_salida(report))

    if not struct_spec:
        # Volcado hex estándar
        raw = file_path.read_bytes()
        console.print(Panel(
            f"[bold cyan]Archivo:[/bold cyan] {file_path.name}\n"
            f"[bold cyan]Tamaño:[/bold cyan] {report.file_size_bytes} bytes\n"
            f"[bold cyan]Hex Preview:[/bold cyan] {raw[:64].hex(' ')}...",
            title="[bold green]KANE Hex Dump[/bold green]"
        ))
        raise typer.Exit(code=_codigo_salida(report))

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
    console.print(f"[dim]Orden de bytes: {report.byte_order}-endian (los campos multibyte se leen así; kane no lo detecta).[/dim]")
    if report.remaining_bytes > 0:
        console.print(f"\n[bold yellow]⚠️ Advertencia: Quedan {report.remaining_bytes} bytes truncados al final del archivo.[/bold yellow]")
    raise typer.Exit(code=_codigo_salida(report))


@app.command("report")
def report_cmd(
    file_path: Path = typer.Argument(..., help="Archivo binario (.bin, .dat) a inspeccionar", exists=True),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Ruta de destino del archivo Markdown."),
    struct_spec: Optional[str] = typer.Option(None, "--struct", "-s", help="Especificación del struct C."),
    header: Optional[Path] = typer.Option(None, "--header", "-H", help="Cabecera .h de la que se lee la definición del struct", exists=True, dir_okay=False),
    struct_name: Optional[str] = typer.Option(None, "--name", "-n", help="Nombre del struct dentro de --header (obligatorio si define varios)"),
    endian: str = typer.Option("little", "--endian", "-e", help="Orden de bytes con que se interpretan los campos multibyte: little o big (no se detecta)"),
):
    """Genera directamente la sección de reporte Markdown de KANE para Dredd."""
    report = _inspeccionar(file_path, struct_spec, header, struct_name, endian)
    md_content = generar_seccion_markdown(report)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(md_content, encoding="utf-8")
        console.print(f"[bold green]✓ Reporte Markdown generado en:[/bold green] {output}")
    else:
        print(md_content)
    raise typer.Exit(code=_codigo_salida(report))


@app.command("doctor")
def doctor_cmd(
    json_output: bool = typer.Option(False, "--json", help="Emitir diagnóstico en formato JSON estructurado."),
) -> None:
    """Verifica el estado del entorno de inspección binaria KANE (Python, xxd/hexdump, GCC)."""
    import shutil
    import sys
    diagnostico = []

    py_ok = sys.version_info >= (3, 10)
    diagnostico.append({
        "componente": "Python Runtime",
        "estado": "OK" if py_ok else "ERROR",
        "requerido": True,
        "detalle": f"Python {sys.version.split()[0]}",
    })

    xxd_path = shutil.which("xxd") or shutil.which("hexdump")
    diagnostico.append({
        "componente": "Herramienta Hexdump (xxd/hexdump)",
        "estado": "OK" if xxd_path else "ADVERTENCIA",
        "requerido": False,
        "detalle": xxd_path or "No encontrado (opcional para volcado hexadecimal interactivo)",
    })

    gcc_path = shutil.which("gcc")
    diagnostico.append({
        "componente": "Compilador GCC",
        "estado": "OK" if gcc_path else "ADVERTENCIA",
        "requerido": False,
        "detalle": gcc_path or "No encontrado (opcional para generar binarios de prueba)",
    })

    todo_ok = py_ok

    if json_output:
        payload = {
            "schema_version": "1.0.0",
            "herramienta": "kane",
            "ok": todo_ok,
            "componentes": diagnostico,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        raise typer.Exit(code=0 if todo_ok else 1)

    tabla = Table(title="🏥 Diagnóstico del Entorno KANE (doctor)", border_style="cyan")
    tabla.add_column("Componente", style="bold white")
    tabla.add_column("Estado", justify="center")
    tabla.add_column("Detalle")

    for c in diagnostico:
        color = "bold green" if c["estado"] == "OK" else ("bold yellow" if c["estado"] == "ADVERTENCIA" else "bold red")
        simbolo = "✓" if c["estado"] == "OK" else ("⚠️" if c["estado"] == "ADVERTENCIA" else "✗")
        tabla.add_row(c["componente"], f"[{color}]{simbolo} {c['estado']}[/{color}]", c["detalle"])

    console.print(tabla)
    if not todo_ok:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
