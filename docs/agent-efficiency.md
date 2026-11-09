# Comparar flujos de agentes

`scripts/check-agent-efficiency.py` ejecuta cinco tareas con datos ficticios en perfiles de
trabajo temporales. Usa MCP stdio, el CLI y la API local del visor. Genera un JSON con cada
ejecución y las medianas por escenario. Solo escribe las mediciones en stdout. Los almacenes,
procesos y registros temporales se retiran al terminar.

## Ejecutar la comparación

Instala el wheel publicado y el wheel candidato en dos entornos Python 3.12 separados.
Usa las restricciones de dependencias de cada bundle y verifica sus sumas publicadas o
preparadas localmente antes de instalar. Desde el repositorio, ejecuta el script con el
intérprete del candidato y pasa el intérprete de la versión anterior:

```powershell
& $candidatePython scripts/check-agent-efficiency.py --baseline-python $baselinePython --repeats 3
```

`--candidate-python` permite elegir otro intérprete con el candidato instalado. Usa
`--repeats 1` para una comprobación rápida. El comando devuelve un código distinto de cero
si falla un escenario o la verificación de lo guardado. Conserva el JSON fuera de Git si
quieres comparar máquinas o revisiones.

La línea base usa las operaciones disponibles en la alpha.7 publicada. El flujo candidato
usa las herramientas de la nueva versión. Se alterna el orden de las versiones y se crean
almacenes equivalentes para cada ronda. Los escenarios se ejecutan en el orden de la tabla.
El tiempo empieza con los procesos preparados y termina al completar el flujo. La recuperación
incluye cerrar la conexión MCP y arrancar el CLI. La preparación y la comprobación directa de los
archivos quedan fuera del tiempo y del número de llamadas.

Las llamadas cuentan intentos de MCP, CLI y HTTP. El tamaño se calcula sobre el JSON compacto
visible para el agente, en caracteres y bytes UTF-8, sin envoltorios de transporte. Una relectura
ocurre cuando un flujo vuelve a leer una nota que ya recibió en un resultado. Los errores de
captura y transporte se contabilizan aparte. Estas son mediciones de flujos guionizados en una
máquina local. No miden tiempo de inferencia, tokens, comportamiento del agente ni del IDE.

## Resultados en Windows

Tres rondas por versión con Python 3.12.14. Línea base del wheel publicado de
[alpha.7](https://github.com/AdanJoGoHe/Shiori/releases/tag/v0.1.0-alpha.7), comparada con el wheel
compilado desde `1a78309c0d852c07dd8db3478e700606e70a8498` tras la #55.

| Flujo | Llamadas antes → después | Bytes antes → después | Mediana antes → después |
|---|---:|---:|---:|
| Retomar una incidencia con su estado, nota y próximo paso | 3 → 1 | 1.645 → 1.048 | 80,81 → 40,85 ms |
| Encontrar un comando literal al fondo de una nota | 2 → 1 | 3.375 → 1.774 | 17,64 → 13,83 ms |
| Guardar una decisión, su avance y el enlace a la ficha | 4 → 2 | 1.500 → 482 | 126,38 → 49,57 ms |
| Editar el estado de una ficha y conservar sus datos | 2 → 2 | 1.194 → 668 | 101,15 → 16,25 ms |
| Recuperar una captura tras perder la respuesta MCP | 3 → 3 | 61 → 61 | 375,47 → 389,29 ms |

- **15 de 15 escenarios por versión** cumplieron sus verificaciones, con cero errores de captura.
- La búsqueda pasó de una relectura del Markdown a recuperar el comando en el primer extracto.
- En la recuperación se descarta el acuse de una escritura confirmada, se cierra MCP y se observa
  un intento fallido de transporte. El CLI recibe el mismo evento, devuelve `duplicate` y la
  comprobación del Diario confirma que quedó una sola entrada en cada ronda.

La recuperación mantuvo el mismo procedimiento en ambas versiones. Las mejoras de las otras
tareas reflejan tanto la elección de herramientas como el trabajo que realiza cada una.
