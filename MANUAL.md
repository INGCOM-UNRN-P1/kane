# Manual de Uso y Referencia Técnica: kane

> **KANE** — Simulador y depurador visual de I/O de bajo nivel y archivos binarios en C
> **Versión:** `0.1.0` · **CLI principal:** `kane` · **Plugin Ripley:** `binary_io`

---

## 1. Arquitectura y Propósito Pedagógico

`kane` forma parte del ecosistema de herramientas de la cátedra de Programación 1 (UNRN). Su objetivo central es resolver de forma modular, determinista y automatizada las tareas asociadas a su dominio específico dentro del ciclo de desarrollo, evaluación y aprendizaje de software en C.

### Alcance Funcional (Qué cubre)
- Depuración, inspección y visualización interactiva de archivos binarios en disco generados por código C.
- Decodificación estructurada de datos binarios mapeando un `struct` C, dado en línea (`--struct`) o leído de una cabecera `.h` (`--header` y `--name`).
- Interpretación de los campos multibyte en little-endian (por defecto) o big-endian (`--endian`). El orden **no se detecta**: lo decide quien sabe qué máquina escribió el archivo, y el reporte lo declara.
- Sin `--struct`/`--header`, `inspect` muestra una vista previa hexadecimal de los primeros 64 bytes (sin anotaciones de campos); el desglose por campo, tamaño, offset y alineación aparece al indicar el struct.
- Representación de bits de valores de C (`kane bits`): enteros con y sin signo (complemento a dos y desborde modular), `float` y `double` (IEEE 754) y operaciones de bits paso a paso.

### Límites de Responsabilidad y Delegación (Qué no cubre)
- Cálculo de padding y alineación teórica en memoria RAM (delegado a `brett`); kane aplica las mismas reglas de alineación de C para ubicar los campos dentro del archivo.
- Auditoría de símbolos en bibliotecas compartidas (delegado a `parker`).
- Verificación de permisos y llamadas al sistema de I/O (delegado a `kaneda`).

### Principios de Diseño
- **Enfoque Pedagógico:** Diagnósticos y mensajes en español rioplatense orientados a facilitar la comprensión de errores conceptuales.
- **Salida Estructurada Dual:** Soporte nativo para visualización enriquecida en terminal (Rich) y salida parseable para orquestadores (`--json`).
- **Integración Contractual:** Capacidad de emitir secciones de reporte para `dredd` (`dredd-section`) y actuar como satélite orquestado por `ripley`.
- **Idempotencia y Robustez:** Validación de precondiciones y comandos de autodiagnóstico (`doctor`) para verificación del entorno.

---

## 2. Instalación y Requisitos

### Requisitos del Sistema
- **Python:** `>= 3.10` (recomendado Python 3.11 o 3.12).
- **Gestor de paquetes:** [`uv`](https://github.com/astral-sh/uv) (entorno estándar de cátedra).
- **Toolchain C (si aplica):** GCC / Clang, Make, GDB y bibliotecas estándar de desarrollo.

### Instalación en el Entorno de Usuario
Para instalar la herramienta de forma global y aislada en el sistema mediante `uv tool`:
```bash
uv tool install git+https://github.com/INGCOM-UNRN-P1/kane
```

### Verificación de Instalación
Ejecutá el comando `doctor` para constatar que todas las dependencias y binarios requeridos estén presentes y operativos:
```bash
kane doctor
```

---

## 3. Guía Integral de Comandos (CLI)

| Comando | Descripción Breve |
| :--- | :--- |
| [`kane check`](#check) | Inspecciona y desglosa el contenido de un archivo binario mapeándolo a un struct C. |
| [`kane inspect`](#inspect) | Inspecciona y desglosa el contenido de un archivo binario mapeándolo a un struct C. |
| [`kane report`](#report) | Genera directamente la sección de reporte Markdown de KANE para Dredd. |
| [`kane doctor`](#doctor) | Verifica el estado del entorno de inspección binaria KANE (Python, xxd/hexdump, GCC). |

### `kane check`

Inspecciona y desglosa el contenido de un archivo binario mapeándolo a un struct C.

#### Argumentos
| Argumento | Tipo | Descripción |
| :--- | :--- | :--- |
| `file_path` | `<class 'pathlib._local.Path'>` | Archivo binario (.bin, .dat) a inspeccionar |

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--struct`, `-s` | `Optional[str]` | `None` | Especificación de struct: 'int id, char nombre[20], float nota' |
| `--json` | `<class 'bool'>` | `False` | Emitir salida en formato JSON estructurado |
| `--md`, `--output-md` | `Optional[pathlib._local.Path]` | `None` | Generar sección de reporte en formato Markdown para fusión en Dredd. |
| `--header`, `-H` | `Optional[pathlib._local.Path]` | `None` | Cabecera .h de la que se lee la definición del struct |
| `--name`, `-n` | `Optional[str]` | `None` | Nombre del struct dentro de --header (obligatorio si define varios) |
| `--endian`, `-e` | `<class 'str'>` | `little` | Orden de bytes con que se interpretan los campos multibyte: little o big (no se detecta) |

#### Ejemplo de Invocación
```bash
kane check <file_path>
```

### `kane inspect`

Inspecciona y desglosa el contenido de un archivo binario mapeándolo a un struct C.

#### Argumentos
| Argumento | Tipo | Descripción |
| :--- | :--- | :--- |
| `file_path` | `<class 'pathlib._local.Path'>` | Archivo binario (.bin, .dat) a inspeccionar |

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--struct`, `-s` | `Optional[str]` | `None` | Especificación de struct: 'int id, char nombre[20], float nota' |
| `--json` | `<class 'bool'>` | `False` | Emitir salida en formato JSON estructurado |
| `--md`, `--output-md` | `Optional[pathlib._local.Path]` | `None` | Generar sección de reporte en formato Markdown para fusión en Dredd. |
| `--header`, `-H` | `Optional[pathlib._local.Path]` | `None` | Cabecera .h de la que se lee la definición del struct |
| `--name`, `-n` | `Optional[str]` | `None` | Nombre del struct dentro de --header (obligatorio si define varios) |
| `--endian`, `-e` | `<class 'str'>` | `little` | Orden de bytes con que se interpretan los campos multibyte: little o big (no se detecta) |

#### Ejemplo de Invocación
```bash
kane inspect <file_path>
```

### `kane report`

Genera directamente la sección de reporte Markdown de KANE para Dredd.

#### Argumentos
| Argumento | Tipo | Descripción |
| :--- | :--- | :--- |
| `file_path` | `<class 'pathlib._local.Path'>` | Archivo binario (.bin, .dat) a inspeccionar |

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--output`, `-o` | `Optional[pathlib._local.Path]` | `None` | Ruta de destino del archivo Markdown. |
| `--struct`, `-s` | `Optional[str]` | `None` | Especificación del struct C. |
| `--header`, `-H` | `Optional[pathlib._local.Path]` | `None` | Cabecera .h de la que se lee la definición del struct |
| `--name`, `-n` | `Optional[str]` | `None` | Nombre del struct dentro de --header (obligatorio si define varios) |
| `--endian`, `-e` | `<class 'str'>` | `little` | Orden de bytes con que se interpretan los campos multibyte: little o big (no se detecta) |

#### Ejemplo de Invocación
```bash
kane report <file_path>
```

### `kane bits`

Muestra cómo queda guardado un valor en un tipo de C, bit a bit: binario agrupado de a 4, hexadecimal,
valor guardado (y su lectura sin signo), bytes en memoria según el orden y una explicación (complemento
a dos de los negativos, desborde módulo 2^n cuando el valor no entra en el tipo). Con `float` y `double`,
el desglose IEEE 754: signo, exponente (con su sesgo), mantisa y clase (normal, subnormal, cero,
infinito, NaN). Si el valor es una expresión con `&`, `|`, `^`, `~`, `<<` o `>>`, muestra cada
operación con los operandos alineados bit a bit.

Las expresiones siguen las reglas de C: cada literal es un valor del tipo elegido y, si el tipo es más
chico que `int` (`char`, `short`, `uint8_t`…), se **promueve a `int`** antes de operar, así que los pasos
se muestran en 32 bits y el resultado se guarda de vuelta en el tipo (por eso `0xF3 << 2 >> 2` en
`unsigned char` da 243 y no 51). `>>` de un valor con signo es aritmético (copia el signo, como gcc); un
`<<` de un negativo o que desborda un tipo con signo se marca como comportamiento indefinido.

#### Argumentos
| Argumento | Descripción |
| :--- | :--- |
| `valor` | Literal de C (`42`, `-7`, `0x2A`, `0b1010`, `052`, `'A'`, `3.5`) o expresión de bits (`'0x0F & 0xF3'`). |

#### Opciones y Banderas
| Opción | Por defecto | Descripción |
| :--- | :--- | :--- |
| `--tipo`, `-t` | `int` | `char`, `short`, `int`, `long long`, `int8_t`…`uint64_t`, `size_t`, `float`, `double` (y sus `unsigned`). `long` no se acepta: mide 64 bits en Linux y 32 en Windows. |
| `--endian`, `-e` | `little` | Orden de los bytes en memoria: `little` (x86, ARM) o `big`. |
| `--json` | — | Salida en JSON (`schema_version`, `resultado` y `pasos`). |

#### Ejemplos
```bash
kane bits -1 -t int8_t          # complemento a dos: 1111 1111
kane bits 300 -t uint8_t        # no entra: se guarda 44 (300 módulo 256)
kane bits 0.1 -t float          # IEEE 754: 0.1 no es exacto en binario
kane bits '0x0F & 0xF3' -t uint8_t
kane bits '~0' -t uint16_t
```

Un valor que no se puede interpretar en el tipo (decimales en un entero, un desplazamiento mayor o
igual que el ancho del tipo) es un error de uso y sale con 2.

### `kane doctor`

Verifica el estado del entorno de inspección binaria KANE (Python, xxd/hexdump, GCC).

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--json` | `<class 'bool'>` | `False` | Emitir diagnóstico en formato JSON estructurado. |

#### Ejemplo de Invocación
```bash
kane doctor
```

---

## 4. Formatos de Salida e Integración con el Ecosistema

### Modo Interactivo / Terminal (Rich)
Por defecto, la herramienta renderiza paneles, árboles y tablas estilizadas para facilitar la lectura del estudiante y docente en terminales modernas con soporte ANSI.

### Modo Estructurado JSON (`--json`)
Para integración con pipelines de CI/CD, scripts de automatización u orquestadores externos, la opción `--json` emite un documento JSON estricto por la salida estándar (`stdout`), dirigiendo cualquier mensaje de logging a `stderr`:
```bash
kane check --json
```

### Integración con Dredd (`dredd-section`)
Cuando la herramienta genera reportes de evaluación para entregas de alumnos, produce una sección Markdown estandarizada conforme al contrato de integración de Dredd (v1.0.0):
```markdown
<!-- dredd-section: kane, tool=kane, version=0.1.0, status=ok -->
```
Este encabezado garantiza la agregación determinista de los hallazgos en la rúbrica docente.

### Integración con Ripley
`kane` está registrada en el catálogo de plugins satélites de Ripley (`SATELLITE_CATALOG`). Puede invocarse directamente a través del motor de evaluación de Ripley configurando el análisis en `ripley.toml`.

---

## 5. Diagnóstico y Códigos de Salida

### Códigos de Retorno (`exit code`)
| Código | Significado |
| :---: | :--- |
| `0` | Ejecución exitosa sin hallazgos críticos ni errores de sintaxis. |
| `1` | Hallazgos pedagógicos detectados, infracción de reglas o advertencias activas. |
| `2` | Error de sintaxis en argumentos CLI o archivo fuente no encontrado. |
| `>2` | Error no recuperable del sistema, fallo de memoria o excepción interna. |

### Diagnóstico del Entorno (`doctor`)
Ante comportamientos inesperados, verificá el estado operativo con:
```bash
kane doctor
```
Comprueba la presencia de las dependencias requeridas y la integridad de los componentes del paquete.