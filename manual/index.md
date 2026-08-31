---
title: "Manual de Referencia: kane"
subtitle: "Kane — Simulador y Depurador Visual de I/O de Bajo Nivel y Perfiles Seccomp"
author: "Cátedra de Algoritmos y Programación"
date: "2026-08-31"
---

(manual-kane)=
# Kane — Simulador y Depurador Visual de I/O de Bajo Nivel y Perfiles Seccomp

````{abstract}
**Rol en el ecosistema:** Inspección de descriptores de archivo, mapeo binario de estructuras en disco, auditoría de syscalls de E/S (`read`, `write`, `lseek`) y filtrado con Seccomp.
````

---

(manual-kane-proposito)=
## 1. Propósito y Filosofía Pedagógica

La herramienta **`kane`** forma parte del ecosistema oficial de software de la cátedra. Su diseño sigue principios pedagógicos rigurosos:

1. **Evidencia Técnica Directa**: Todo diagnóstico se fundamenta en la norma ISO C (C11/C23), en el modelo de memoria del sistema o en convenciones arquitectónicas formales.
2. **Acción Correctiva Concreta**: Cada advertencia incluye la prescripción técnica inmediata para resolver el defecto sin recurrir a conjeturas.
3. **Autonomía del Estudiante**: Facilita la autoevaluación local antes de la entrega final del trabajo práctico.
4. **Objetividad Docente**: Estandariza la corrección automática eliminando discrepancias subjetivas en la evaluación.

---

(manual-kane-instalacion)=
## 2. Instalación y Diagnóstico del Entorno

````{important}
Asegurate de contar con el compilador GCC/Clang y las librerías del sistema instaladas antes de ejecutar `kane`.
````

Para comprobar el estado de salud de tu entorno de trabajo y las dependencias auxiliares:

````{code-block} bash
# Comprobación de dependencias del sistema
kane doctor
````

Si se detecta la falta de alguna utilidad (como `gdb`, `valgrind`, `clang-format` o `typst`), el comando indicará el paquete exacto a instalar según tu distribución GNU/Linux o entorno MSYS2.

---

(manual-kane-comandos)=
## 3. Referencia Completa de Comandos CLI

A continuación se detallan los subcomandos principales disponibles en `kane`:

| Sintaxis del Comando | Descripción y Efecto |
| :--- | :--- |
| `kane trace -- ./bin/programa` | Monitorea en tiempo real todas las operaciones de archivos y descriptores. |
| `kane dump-struct <archivo.bin> --format <struct_header.h>` | Mapea un archivo binario a campos de la struct C. |
| `kane audit-fds -- ./bin/servidor` | Detecta descriptores de archivo abiertos que no fueron cerrados con close/fclose. |
| `kane doctor` | Verifica el soporte de ptrace y seccomp en el kernel Linux. |

````{tip}
Podés agregar el flag `--json` a la mayoría de los comandos para exportar resultados en formato estructurado o `--md` para generar reportes Markdown para el informe de entrega.
````

---

(manual-kane-tutorial)=
## 4. Tutorial Paso a Paso con Ejemplos Reales

### Caso de Estudio

Considerá el siguiente fragmento de código representativo:

````{code-block} c
:linenos:
#include <stdio.h>
#include <fcntl.h>
#include <unistd.h>

struct Registro {
    int legajo;
    float nota;
};

void guardar(const char *path) {
    int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    struct Registro r = {12345, 9.5f};
    write(fd, &r, sizeof(r));
    // Falta close(fd) -> Kane alertará fuga de FD
}
````

### Ejecución de la Herramienta

Ejecutá el análisis desde tu terminal:

````{code-block} bash
kane trace -- ./bin/programa
````

### Salida Obtenida en Consola

````{code-block} text
[!] KANE FD AUDITOR: Descriptor de archivo no liberado:
    • FD #3 abierto en main.c:10 (open('datos.bin')) nunca fue cerrado antes del fin del proceso.

[✓] Mapeo de Struct en datos.bin (8 bytes):
    ├─ legajo: 12345 (0x00003039)
    └─ nota: 9.500000 (0x41180000)
````

````{note}
Prestá atención a la explicación pedagógica generada: la herramienta no solo señala la línea del problema, sino que explica la causa raíz y el impacto en memoria o arquitectura.
````

---

(manual-kane-ejercicios)=
## 5. Ejercicios Prácticos y Desafíos

Practicá el uso avanzado de **`kane`** resolviendo los siguientes ejercicios:

````{exercise} Desafío 1: Detección de Fugas de Descriptores (FD Leaks)
Encontrar archivos abiertos con `fopen` que no tienen `fclose`.

**Instrucción de ejecución:**
```bash
kane audit-fds -- ./bin/app_archivos
```
````

````{solution} Desafío 1
```bash
kane audit-fds -- ./bin/app_archivos
# Verificá que la operación concluya exitosamente con código de salida 0.
```
````

````{exercise} Desafío 2: Inspección Hexadecimal de Archivo Binario
Mapear un archivo `.dat` con la definición de `struct Alumno`.

**Instrucción de ejecución:**
```bash
kane dump-struct alumnos.dat --format include/alumno.h
```
````

````{solution} Desafío 2
```bash
kane dump-struct alumnos.dat --format include/alumno.h
# Revisá el archivo generado o el informe en terminal para confirmar la resolución del problema.
```
````

````{exercise} Desafío 3: Auditoría de Llamadas al Sistema de E/S
Monitorear offsets y bytes transferidos en operaciones `lseek`.

**Instrucción de ejecución:**
```bash
kane trace -- ./bin/lector_indices
```
````

````{solution} Desafío 3
```bash
kane trace -- ./bin/lector_indices
# Comprobá que la salida confirme la ausencia de advertencias o errores pendientes.
```
````

---

(manual-kane-makefile)=
## 6. Integración en el Flujo de Trabajo y Makefile

Para incorporar `kane` de forma automática a tu flujo de desarrollo, agregá la siguiente regla en el `Makefile` de tu proyecto:

````{code-block} makefile
check-kane:
	@echo "=== Ejecutando verificación con kane ==="
	kane check src/ include/

.PHONY: check-kane
````

Ejecutá `make check-kane` antes de cada commit para asegurar que tu código conserve el estado de aprobación.

---

(manual-kane-arquitectura)=
## 7. Arquitectura Interna y Mecanismo Técnico

La herramienta **`kane`** implementa un motor de alta precisión basado en:

- **Tecnología Núcleo:** `Linux ptrace Syscall Interceptor + Struct Memory Binary Unpacker + Seccomp BPF Filter`.
- **Aislamiento y Determinismo:** Diseñada para operar sin efectos colaterales en entornos de integración continua (CI), terminales de estudiantes y servidores docentes headless.
- **Manejo de Errores Pedagógico:** Todo fallo de sintaxis, memoria o lógica se traduce en una acción prescriptiva concreta con su respectiva justificación técnica.

---

(manual-kane-ecosistema)=
## 8. Integración y Conexión con el Ecosistema

````{note}
Ninguna herramienta opera de forma aislada. **`kane`** forma parte del pipeline integral de evaluación, verificación y enseñanza de la cátedra.
````

### Diagrama de Flujo e Interoperabilidad

````{mermaid}
graph TD
    DAT[Archivos Binarios .dat/.bin] --> KAN[Kane: Depurador de E/S]
    HDR[Headers C: Structs] --> KAN
    KAN -->|Auditoría de Descriptores| PTRACE[Linux ptrace Engine]
    KAN -->|Layout en Disco| BRT[Brett: Auditor de Structs]
    KAN -->|Perfiles Seccomp BPF| NOS[Nostromo: Sandbox Seguro]
````

### Matriz de Intercambio de Datos

| Canal | Herramientas Conectadas | Tipo de Datos Transferidos |
| :--- | :--- | :--- |
| **Entradas (Inputs)** | - `Binarios C y archivos de datos en disco (.bin, .dat)` | Código fuente, AST, binarios, testcases, contratos |
| **Salidas (Outputs)** | - `brett (verificación de layout en disco)`
- `nostromo (perfiles seccomp)` | Informes Markdown, diagnósticos Rich, JSON, actas |
| **Sincronización** | `brett`, `nostromo`, `crowe` | Validación cruzada, flags compartidos y autofix |

### Pipeline de Integración Recomendado

Podés encadenar `kane` con otras herramientas del ecosistema en una única línea de comando:

````{code-block} bash
# Pipeline de integración típico
kane dump-struct alumnos.dat --format include/alumno.h
````

