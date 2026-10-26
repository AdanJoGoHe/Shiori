# Shiori

Shiori es el nuevo nombre de Second Brain. Sirve para guardar lo que aprendes y encontrarlo
después.

**Vuelve a lo que aprendiste.**

## El nombre y el icono

Shiori (栞) significa marcapáginas o guía. Nos gustó la idea de marcar algo para volver a ello:
un comando útil, una dirección o una nota. [Entrada de diccionario](https://kotobank.jp/word/栞-897522).

- Icono: una hoja con una esquina doblada y forma de marcapáginas. [SVG](../assets/shiori-mark.svg).
- Nombre: Shiori, con mayúscula inicial. El kanji acompaña la explicación y no sustituye el
  nombre legible en la interfaz.
- Textos: frases cortas y palabras normales. Explicar qué puedes hacer sin sonar a anuncio
  ni a documento de empresa. Los detalles técnicos van en la guía que corresponda.
- Temas: Claro, Oscuro y Café Latte conservan sus paletas y preferencias existentes. La marca
  hereda la tinta de cada tema. Segoe UI para controles; Georgia para el nombre, disponible localmente.

El nombre aparece en la biblioteca y la conexión MCP, donde figura como Shiori Personal.
Puedes seguir usando las mismas búsquedas, marcas y categorías.

## Compatibilidad

| Parte | Qué se mantiene |
|---|---|
| Comando recomendado | `shiori`, disponible al instalar o actualizar |
| Comando anterior | `second-brain`, funciona igual |
| Paquete / módulo | `second-brain` / `second_brain`, sin cambio de dependencias |
| Repositorio y enlaces | `AdanJoGoHe/Shiori`, repositorio público desde una raíz revisada, sin el historial privado |
| MCP y herramientas | Entrada `second_brain_personal`, herramientas y permisos actuales |
| Skill / bloques gestionados | `second-brain` y marcadores `SECOND BRAIN PERSONAL` |
| Datos y configuración | Vault, estado, config, variables `SECOND_BRAIN_*` y esquemas actuales |
| Tema guardado | Clave `second-brain-theme`, conserva la elección previa |
| Copias y transferencia | Mismo manifiesto, ledger, exportación/importación agregativa y restauración |

Si ya lo tenías instalado, puedes dejar tus notas y ajustes donde están. Sigue
los [pasos para actualizar](actualizacion.md) con tu configuración actual.
Un proceso que ya estaba abierto puede mostrar el nombre anterior hasta que lo reinicies.

## Identidad en GitHub

El código está en **AdanJoGoHe/Shiori**, con un historial nuevo. El trabajo anterior se conserva
en un archivo privado. [Aquí se explica qué incluye Shiori](specification.md).
Si tienes un clon antiguo, consulta [cómo cambiar al repo público](actualizacion.md#cambio-de-repositorio-en-github).

## Comprobación visual

El icono usa el color de texto de cada tema. No descarga fuentes ni imágenes de otros sitios.
Las pruebas usan notas de ejemplo y distintos tamaños de pantalla. Para repetirlas, consulta
[cómo ejecutar las pruebas](test-report.md) y [las pruebas de la biblioteca](explorer-acceptance.md).
