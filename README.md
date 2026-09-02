# KANE — Simulador y Depurador Visual de I/O Binario en C

**KANE** inspecciona archivos binarios generados por programas C (`fread`, `fwrite`), desglosando sus registros en tablas legibles mapeadas a definiciones de `struct` C con offsets hexadecimales y detección de bytes truncados.

---

## 🎯 Alcance

### Qué cubre
- Depuración, inspección y visualización interactiva de archivos binarios en disco generados por código C.
- Decodificación estructurada de datos binarios mapeando definiciones de `struct` declaradas en archivos de cabecera C (`.h`).
- Detección y visualización pedagógica de ordenamiento de bytes (Little Endian vs Big Endian).
- Volcado hexadecimal anotado (Hex Dump) con colores en terminal Rich indicando campos, tamaños y alineación.

### Qué no cubre (Límites y Delegación)
- Cálculo de padding y alineación teórica en memoria RAM (delegado a `brett`).
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
```
