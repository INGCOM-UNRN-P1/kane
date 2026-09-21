# KANE — Simulador y Depurador Visual de I/O Binario en C

**KANE** inspecciona archivos binarios generados por programas C (`fread`, `fwrite`), desglosando sus registros en tablas legibles mapeadas a definiciones de `struct` C con offsets hexadecimales y detección de bytes truncados.

---

## 🎯 Alcance

### Qué cubre
- Depuración, inspección y visualización interactiva de archivos binarios en disco generados por código C.
- Decodificación estructurada de datos binarios mapeando un `struct` C, dado en línea (`--struct`) o leído de una cabecera `.h` (`--header` y `--name`).
- Interpretación de los campos multibyte en little-endian (por defecto) o big-endian (`--endian`). El orden **no se detecta**: lo decide quien sabe qué máquina escribió el archivo, y el reporte lo declara.
- Sin `--struct`/`--header`, `inspect` muestra una vista previa hexadecimal de los primeros 64 bytes (sin anotaciones de campos); el desglose por campo, tamaño, offset y alineación aparece al indicar el struct.

### Qué no cubre (Límites y Delegación)
- Cálculo de padding y alineación teórica en memoria RAM (delegado a `brett`); kane aplica las mismas reglas de alineación de C para ubicar los campos dentro del archivo.
- Auditoría de símbolos en bibliotecas compartidas (delegado a `parker`).
- Verificación de permisos y llamadas al sistema de I/O (delegado a `kaneda`).

---

## 📋 Requisitos

### Requisitos de Sistema y Entorno
- Multiplataforma. Python >= 3.10.

### Dependencias Externas y Binarios
- Ninguno obligatorio.

### Integración en el Ecosistema
- CLI `kane`. Plugin registrado en `ripley.plugins` (`binary_io`).

---

## 🚀 Uso Rápido

```bash
# Inspección con mapeo a estructura C
kane inspect datos.bin --struct "int id, char nombre[30], double promedio"

# Hex dump rápido
kane inspect datos.bin

# Salida estructurada JSON
kane inspect datos.bin --struct "int id, float nota" --json

# Struct leído de una cabecera .h (si define varios, elegí uno con --name)
kane inspect alumnos.bin --header alumno.h --name Alumno

# Archivo escrito por una máquina big-endian
kane inspect red.bin --struct "int id, short puerto" --endian big
```

### Qué se puede mapear

- Escalares: `char`, `signed/unsigned char`, `short`, `int`, `long`, `long long` (con `unsigned`), `float`, `double`, `bool`, `enum` (como `int`) y los `stdint` (`int8_t`…`uint64_t`, `size_t`).
- Arreglos de una dimensión de cualquier escalar (`int notas[3]`, `char nombre[20]`); la dimensión puede ser un número o un `#define` numérico de la propia cabecera.
- El layout supone el ABI LP64 de x86-64 Linux (`long` = 8 bytes) e incluye el padding que inserta el compilador.
- **No se soportan** (y kane lo informa con un error en vez de adivinar): punteros, struct/union anidados, bit-fields, arreglos multidimensionales, `long double` y tipos que no sean los de arriba.
