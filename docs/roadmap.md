# Próximos pasos

Las siete tareas del [roadmap #49](https://github.com/AdanJoGoHe/Shiori/issues/49) están completas.
Las [notas de alpha.8](releases/v0.1.0-alpha.8.md) recogen las fichas, checkpoints, búsqueda local,
guías de trabajo y captura opcional del Agent Log. Consulta las
[releases publicadas](https://github.com/AdanJoGoHe/Shiori/releases) para descargar una versión.

## Prioridades

1. [Comprobar Augment JetBrains](https://github.com/AdanJoGoHe/Shiori/issues/2): verificar el
   MCP y la skill dentro de una versión concreta del IDE/plugin. El perfil local de trabajo
   ya existe y mantiene su memoria separada; las pruebas sintéticas no completan esta tarea.
2. Mantener claras la [compatibilidad](compatibility.md) y las [guías](guia-de-usuario.md):
   distinguir versiones publicadas, cambios pendientes y pruebas realmente realizadas.

La memoria personal excluye material corporativo. Un perfil de trabajo separado se usa solo
en un entorno permitido y no comparte almacén ni índice con el personal.

## Más adelante

La conexión remota es opcional y se ha decidido empezar en local. Existe una base HTTP
autenticada; el cliente remoto gestionado y la prueba real desde dos equipos siguen pendientes.
La [guía remota](remote-mcp.md) describe los límites. No hace falta activar una VPN para usar
Shiori en local; la [transferencia agregativa](memory-transfer.md) permite pasar notas aparte.

Los hooks de captura, la aceptación en otros hosts y la compatibilidad estable necesitan sus
propias pruebas. El historial de diario ya tiene una vista visual; un grafo de conocimiento
sería trabajo adicional, no un requisito para instalar la alpha.

Las tareas actuales se siguen en [GitHub Issues](https://github.com/AdanJoGoHe/Shiori/issues).
Los identificadores `SB-*` y los números del repositorio anterior son referencias históricas.
Una tarea de aceptación no está completa solo porque exista su código.
