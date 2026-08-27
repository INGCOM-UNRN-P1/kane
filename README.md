# KANE — Simulador y Depurador Visual de I/O Binario en C

**KANE** inspecciona archivos binarios generados por programas C (`fread`, `fwrite`), desglosando sus registros en tablas legibles mapeadas a definiciones de `struct` C con offsets hexadecimales y detección de bytes truncados.

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
