"""Run the local viewer with disposable synthetic content, never the personal vault."""

import tempfile
from datetime import timedelta
from pathlib import Path

from second_brain.core import Brain
from second_brain.task_pages import TaskPages
from second_brain.viewer import Viewer, serve_viewer


def main():
    with tempfile.TemporaryDirectory(prefix="second-brain-viewer-demo-") as directory:
        root = Path(directory).resolve()
        assert root.is_relative_to(Path(tempfile.gettempdir()).resolve())
        docs = root / "docs"
        docs.mkdir()
        documents = {
            "instalacion.md": """---
tags: [python, windows]
project: second-brain
---
# Guía de instalación

Datos de demostración para validar el lector. Los archivos Markdown permanecen en el equipo.

## Preparar el entorno

Usa un entorno aislado para separar las dependencias del proyecto.

```powershell
python -m venv .venv
echo "Listo 😀"
```

También hay `código en línea` para seleccionar. Primera aparición: texto repetido.
Segunda aparición: texto repetido.

## Comprobar el resultado

| Comprobación | Resultado esperado |
| --- | --- |
| Documentación | Disponible localmente |
| Búsqueda | Funciona sin nube |
| Escritura | Deshabilitada en el visor |

Consulta las [decisiones de arquitectura](arquitectura.md).
""",
            "arquitectura.md": """---
tags: [markdown, local]
project: second-brain
---
# Decisiones de arquitectura

Datos de demostración. Markdown es la fuente de verdad.

## Separar lectura y captura

El visor consulta contenido autorizado. Las lecciones pasan por la captura validada.
""",
            "busqueda.md": "# Búsqueda y filtros\n\nDatos de demostración. Combina términos, etiquetas, proyecto y fechas.",
        }
        for name, body in documents.items():
            (docs / name).write_text(body, encoding="utf-8")
        brain = Brain(
            {
                "scope": "personal",
                "vault_path": str(root / "vault"),
                "state_path": str(root / "state"),
                "timezone": "Europe/Madrid",
                "documentation_roots": {"demo-docs": str(docs)},
            }
        )
        moment = brain.now()
        brain.now = lambda: moment  # Keep this disposable fixture on one day, even at midnight.
        for note_id, title, status, tags in [
            ("utf8-windows", "UTF-8 en Windows", "verified", ["python", "windows"]),
            ("notas-con-evidencia", "Notas con evidencia", "unverified", ["markdown"]),
        ]:
            result = brain.capture(
                {
                    "scope": "personal",
                    "id": note_id,
                    "event_id": note_id,
                    "title": title,
                    "type": "knowledge",
                    "status": status,
                    "source_agent": "codex",
                    "body": "Datos de demostración para probar lectura y búsqueda.",
                    "evidence": "Fixture sintético; no representa una comprobación del equipo.",
                    "tags": tags,
                    "project": "second-brain",
                }
            )
            assert result["status"] == "saved"
        viewer = Viewer(brain)
        assert viewer.items({})["total"] == 6
        document = viewer.content("documentation:demo-docs:instalacion.md")
        for quote, category, color in [
            ('python -m venv .venv\necho "Listo 😀"', "comando", "green"),
            (
                "Usa un entorno aislado para separar las dependencias del proyecto.",
                "informacion-importante",
                "yellow",
            ),
        ]:
            start = document["text"].index(quote)
            viewer.annotations.save(
                document,
                dict(
                    document_id=document["item"]["id"],
                    revision=document["revision"],
                    start=start,
                    end=start + len(quote),
                    quote=quote,
                    color=color,
                    tags=[category],
                ),
            )
        command_mark = next(
            mark for mark in viewer.annotations.export()["items"] if "comando" in mark["tags"]
        )
        TaskPages(brain).save(
            dict(
                key="DEMO-1234",
                title="Preparar el entorno de ejemplo",
                status="in-progress",
                body="## Contexto\n\nFicha ficticia para probar notas, marcas y referencias.\n\n"
                "## Comprobar\n\n```powershell\npython -m venv .venv\n```\n",
                project="second-brain",
                tags=["demo", "entorno"],
                version=0,
                links=[
                    dict(
                        target=command_mark["document_id"],
                        annotation_id=command_mark["id"],
                        label="Comando de instalación",
                    ),
                    dict(
                        target="https://example.test/issue/DEMO-1234",
                        annotation_id=None,
                        label="Incidencia de ejemplo",
                    ),
                ],
            )
        )
        base = dict(
            scope="personal", mode="journal-only", source_agent="manual", project="second-brain"
        )
        task = dict(
            id="editor-demo", title="Comprobar el lector", details="Usar un ejemplo ficticio"
        )
        brain.now = lambda: moment - timedelta(days=180)
        brain.capture(
            dict(
                base,
                event_id="demo-archive",
                title="Primera guía de ejemplo revisada",
                summary="Avance ficticio antiguo para probar la navegación por meses.",
                progress={"completed": ["Preparada la primera guía del laboratorio."]},
            )
        )
        brain.now = lambda: moment - timedelta(days=2)
        brain.capture(
            dict(
                base,
                event_id="demo-day-start",
                activity="lector",
                title="Lector preparado",
                summary="Preparado el documento de ejemplo para revisar las marcas.",
                tasks=[dict(task, status="open", version=0)],
                progress={"completed": ["Creado un documento con un comando multilínea."]},
            )
        )
        brain.now = lambda: moment - timedelta(days=1)
        brain.capture(
            dict(
                base,
                event_id="demo-day-blocked",
                activity="lector",
                title="Marcas revisadas",
                summary="Las marcas conservan el texto. Queda pendiente la vuelta desde el lector.",
                tasks=[dict(task, status="blocked", version=1)],
                progress={
                    "checks": ["Copia exacta del comando comprobada."],
                    "blockers": ["Revisar la vuelta con el teclado."],
                },
            )
        )
        brain.now = lambda: moment
        brain.capture(
            dict(
                base,
                event_id="demo-day-done",
                activity="lector",
                title="Lector comprobado",
                summary="Se puede abrir una marca y volver al resultado sin perder el contexto.",
                tasks=[dict(task, status="done", version=2)],
                progress={
                    "completed": ["Conservados los filtros al volver del lector."],
                    "checks": ["Navegación con teclado y copia exacta comprobadas."],
                    "decisions": ["Mantener los archivos Markdown como fuente."],
                },
            )
        )
        brain.capture(
            dict(
                base,
                event_id="demo-day-next",
                activity="paquete",
                title="Paquete de ejemplo preparado",
                summary="Preparada una instalación ficticia para revisar la guía.",
                tasks=[
                    dict(
                        id="guia-demo",
                        title="Revisar la guía de instalación",
                        details="Comprobar los pasos con datos ficticios",
                        status="open",
                        version=0,
                    )
                ],
                progress={
                    "blockers": ["Falta revisar la guía en una instalación nueva."],
                    "next_steps": ["Seguir la guía con un entorno desechable."],
                },
            )
        )
        serve_viewer(brain)


if __name__ == "__main__":
    main()
