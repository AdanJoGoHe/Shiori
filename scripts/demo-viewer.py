"""Run the local viewer with disposable synthetic content, never the personal vault."""

import tempfile
from pathlib import Path

from second_brain.core import Brain
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
        serve_viewer(brain)


if __name__ == "__main__":
    main()
