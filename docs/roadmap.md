# Próximos pasos

La versión publicada es [alpha.5](https://github.com/AdanJoGoHe/Shiori/releases/tag/v0.1.0-alpha.5).
Incluye diario visual, pendientes y retomar proyectos. El código de `main` añade las mejoras
del CLI de la [PR #18](https://github.com/AdanJoGoHe/Shiori/pull/18); se prepara alpha.6 para
distribuirlas. Cambiar el código o preparar un paquete no actualiza una instalación existente.

## Prioridades

1. [Preparar alpha.6](https://github.com/AdanJoGoHe/Shiori/issues/20): comprobar el paquete
   instalado y la actualización desde alpha.5, con rollback y datos ficticios. Publicarla será
   un paso explícito después de revisar los resultados.
2. [Comprobar Augment JetBrains](https://github.com/AdanJoGoHe/Shiori/issues/2): verificar el
   MCP y la skill dentro de una versión concreta del IDE/plugin. El perfil local de trabajo
   ya existe y mantiene su memoria separada; las pruebas sintéticas no completan esta tarea.
3. Mantener claras la [compatibilidad](compatibility.md) y las [guías](guia-de-usuario.md):
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
