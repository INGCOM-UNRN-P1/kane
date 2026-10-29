# Changelog

Todos los cambios notables de este proyecto se documentan en este archivo.
Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/);
versiones según [SemVer](https://semver.org/lang/es/).

## [Sin publicar]

### Agregado

- `--abi` en `inspect`, `diff` y la sección para dredd: el tamaño y la alineación de cada tipo salen de la tabla por ABI de brett (`x86_64`, `x86_64-windows`, `i386`, `aarch64`, `riscv64`); el reporte JSON informa la ABI (Ola 28, QoL #81).

### Cambiado

- `TYPE_MAP` ya no tiene tamaños: sólo el formato de `struct` (con o sin signo); el ancho de los enteros sale del tamaño en la ABI. La alineación ya no se supone igual al tamaño (`double` en i386).
- brett fijado en `044dfa4` (publicado, con `ABIS`).

## [0.2.0] - 2026-09-28

Primera versión con registro de cambios; lo anterior está en el historial de git.

### Agregado

- **cli**: cumplir el contrato de línea de comandos de LINEAMIENTOS §3.2 (N-ECO-04) (`7da1593`)

### Documentación

- agregar el texto de la licencia GPL-3.0-or-later que declara pyproject (N-ECO-06) (`67eed9f`)
- incorporar manual de uso integral y referencia tecnica (kane) (`ee58c59`)

### Mantenimiento

- **calidad**: verificar errores de Python y dependencias vulnerables (N-ECO-08, N-ECO-13) (`886d4d2`)
