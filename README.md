# Shiori

<img src="assets/shiori-mark.svg" width="48" height="54" alt="Marcapáginas de Shiori">

Guarda comandos, notas y lo que vas aprendiendo. Encuéntralo después, tú o tus agentes de IA.

Ese comando que funcionó, cómo arreglaste un problema o por qué elegiste una solución.
Shiori te ayuda a guardar esas cosas y tenerlas a mano cuando vuelvas a necesitarlas.
Puedes buscar desde el navegador, la terminal o Codex.

## Qué puedes hacer

- Guardar notas en Markdown y llevar un diario de lo que vas haciendo.
- Marcar comandos, IPs, rutas o cualquier trozo de texto con colores y etiquetas.
- Encontrar esas marcas, ver un poco de contexto y copiar solo lo que necesitas.
- Dejar que tu agente consulte notas anteriores y guarde lo que merece la pena recordar.
- Hacer copias y pasar notas entre instalaciones. Al importar, lo que ya tienes se conserva.
- Elegir entre los temas Claro, Oscuro y Café Latte.

## Empezar

La [guía de instalación y uso](docs/guia-de-usuario.md) te lleva paso a paso.
Los paquetes están en [Releases](https://github.com/AdanJoGoHe/Shiori/releases).
Las versiones alpha aparecen como prerelease; revisa sus notas antes de instalar o actualizar.
Por ahora, la instalación está pensada para Windows, PowerShell, Python 3.12 y Codex.

Una vez instalado, estos comandos sirven para ver el estado, buscar y abrir la biblioteca:

```powershell
Set-Location 'D:\repo\memory'
.\.venv\Scripts\shiori.exe status
.\.venv\Scripts\shiori.exe search 'git'
.\.venv\Scripts\shiori.exe viewer
```

Cambia la carpeta del ejemplo por la tuya. `viewer` muestra una dirección local para abrir
la biblioteca; para cerrarlo desde la terminal, pulsa `Ctrl+C`.

Si ya lo tenías instalado como Second Brain, los comandos `shiori` y `second-brain` hacen
lo mismo. Tus notas y ajustes siguen en sus carpetas. Consulta [cómo actualizar](docs/actualizacion.md)
y, si tienes un clon antiguo, [el cambio de historial](docs/actualizacion.md#cambio-de-repositorio-en-github).

## Para usarlo con un agente

La instalación conecta Shiori con Codex mediante MCP y añade una skill que le explica
cuándo buscar y guardar. Después de instalar, reinicia Codex para que cargue la conexión.

Puedes pedirle algo como:

> Busca en Shiori cómo resolvimos este problema la última vez.

O, al terminar:

> Guarda el comando que funcionó, para qué sirve y qué necesitamos para usarlo.

El agente decide qué consultar y qué proponer para guardar. No es una grabación automática
de todo lo que haces. También puedes usar la CLI sin conectar ningún agente.

## Tus datos

Las notas se guardan en tu equipo, fuera del código. Puedes leerlas como archivos Markdown.
Los colores y etiquetas de fragmentos se guardan aparte, sin cambiar los documentos originales.

Si un agente lee una nota, ese texto llega al proveedor de IA que estés usando. Evita guardar
contraseñas, claves o datos de clientes. El filtro de secretos ayuda, pero no lo detecta todo.

Para proteger o mover tus notas:

- [Copias y restauración](docs/backup-restore.md).
- [Exportar e importar notas](docs/memory-transfer.md), añadiendo las nuevas sin reemplazar las tuyas.
- [Actualizar una instalación](docs/actualizacion.md).
- [Aprender procedimientos y convertirlos en skills](docs/learning.md).
- [Diario de avances y resúmenes por día o semana](docs/diario.md).

## Cómo va el proyecto

Shiori está en alpha y, por ahora, se centra en el uso personal con Codex.
Hay un [perfil separado para Augment en el trabajo](docs/augment-trabajo.md), con instalación
y un updater que descarga versiones publicadas y conserva copias para volver atrás. La aceptación real en Claude y Augment sigue pendiente. La conexión remota entre equipos tiene una
base implementada, pero aún falta probar el despliegue completo. [Más sobre el servidor opcional](docs/remote-mcp.md).

El código es público. La memoria personal se queda fuera del repositorio.
Las pruebas se ejecutan en local; Actions se reserva para casos concretos y releases.

## Para seguir mirando

- [Guía de uso](docs/guia-de-usuario.md): instalación, búsquedas, marcas y ejemplos.
- [Biblioteca y anotaciones](docs/viewer.md).
- [Qué está probado y qué falta](docs/compatibility.md).
- [Próximos pasos](docs/roadmap.md).
- [Contribuir](CONTRIBUTING.md) y [preparar una release](docs/release-workflow.md).

El nombre **Shiori** viene de 栞, «marcapáginas». [Un poco más sobre el nombre](docs/branding.md).
