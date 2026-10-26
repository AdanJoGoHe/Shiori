# Validación local y uso excepcional de GitHub Actions

Política acordada el 2026-10-20: el trabajo habitual se valida en local. Un push, una PR o una
actualización de documentación no inicia Actions. No lanzar una ejecución remota solo para
obtener un check verde ni reintentar ejecuciones bloqueadas por presupuesto.

## Qué usar y cuándo

| Trabajo | Validación |
|---|---|
| Cambio habitual de código o bug reproducible localmente | Lint, formato, tests relevantes y suite local antes de integrar |
| Documentación | Enlaces, ejemplos o contratos afectados; sin Actions |
| Interfaz | API/tests locales y navegador con datos sintéticos |
| Empaquetado, instalación o recuperación | Build y `scripts/verify-release.py` desde un wheel instalado en un entorno sintético separado |
| Regresión que no se reproduce localmente o límite específico de plataforma | Actions manual con motivo y una plataforma; ambos sistemas solo si la comparación es necesaria |
| Preparación/publicación de release | Workflow Release manual desde main; Windows y Linux conservan su aceptación |

La revisión y la evidencia local del commit final sustituyen la antigua convención de exigir CI
remota a cada PR. No marcar checks no ejecutados como aprobados. Las pruebas locales de Windows
no demuestran compatibilidad Linux ni ejecución física bajo MSIX/otros hosts. Si la aceptación
exige esa evidencia, conservar la limitación o solicitar explícitamente la ejecución excepcional.

## Comando local habitual

Desde un checkout con Python3.12 y dependencias de desarrollo instaladas con `uv sync --locked
--extra dev`:

```powershell
.\.venv\Scripts\python.exe scripts/check-local.py
```

En Linux/macOS usa `.venv/bin/python scripts/check-local.py`. El script usa su propio intérprete,
ejecuta Ruff, formato, pytest y el arranque `--help`, y se detiene ante el primer error. No inicia
Actions ni instala/configura/reinicia el despliegue personal. Para cambios pequeños durante el
desarrollo se pueden ejecutar primero pruebas dirigidas; documenta qué se comprobó antes de integrar.

Si afecta a paquetes, además construye e instala el wheel en un entorno distinto del editable:

```powershell
uv build
uv export --locked --no-dev --no-emit-project --no-hashes --output-file release-constraints.txt
uv venv .release-env --python 3.12
uv pip install --python .release-env --constraint release-constraints.txt (Get-ChildItem dist/*.whl).FullName
.\.release-env\Scripts\python.exe scripts/verify-release.py
```

Usa un directorio de build limpio y el wheel exacto del commit revisado; evita mezclar versiones
antiguas en `dist`. El verificador solo usa fixtures sintéticos y requiere un wheel no editable.
La aceptación de navegador y de hosts reales sigue siendo independiente del script de checks.

## Ejecución excepcional

En **Actions → Exceptional validation → Run workflow**, selecciona la rama/commit que quieres
contrastar, explica el motivo y elige `linux` (predeterminado), `windows` o `both`. No hay selección
automática por etiquetas de PR ni calendarios. Los agentes deben tener autorización explícita para
una ejecución remota concreta; trabajar en una issue o abrir una PR no la implica.

El workflow `validate.yml` también es reutilizable por Release. Está limitado a lectura, cancela
validaciones obsoletas del mismo workflow/rama y usa fail-fast con un máximo de un job simultáneo.
Cada job tiene timeout de15 minutos; ambas plataformas solo se seleccionan expresamente. Los runners
se fijan a Ubuntu24.04 y Windows2025 para evitar cambios implícitos de `latest`.

La caché de uv depende de `uv.lock`, se separa por plataforma mediante setup-uv y se poda antes de
persistir. No se cachean vaults, configuraciones, sesiones ni artefactos del propietario; no se suben
artefactos de tests a Actions. Todas las actions se fijan por SHA y uv por versión. Las ejecuciones
manuales y su almacenamiento todavía están sujetos al presupuesto de GitHub; esta política no lo
amplía ni cambia facturación.

El antiguo workflow queda como **Retired CI** (`ci.yml`), con un trigger manual inerte y un job
que siempre se omite sin asignar runner. Mantener su registro desactivado en GitHub evita que los
pushes de ramas antiguas, que todavía contienen los triggers automáticos, reactiven el gasto.
Conservar este archivo permite desactivar el registro: borrarlo hace que GitHub lo marque como
`deleted` y rechace la desactivación explícita. No reactivar el workflow antiguo ni borrar este
resguardo; usar `Exceptional validation` para la excepción autorizada.

## Releases sin duplicación

Release solo admite dispatch manual y `publish=false` por defecto. Fuera de main no se asigna
ningún runner. En main valida Windows con el workflow reutilizable; después el job de Linux ejecuta
los mismos checks locales, construye y audita los artefactos y prueba ese wheel exacto antes de crear
el borrador. Son dos jobs de plataforma, frente a los tres anteriores (Linux+Windows y Linux de nuevo).
La publicación sigue serializada sin cancelar una publicación iniciada; no se sobrescriben tags ni
releases. No ejecutar Release como sustituto de una validación ordinaria.

Validación de esta política: tests de contratos YAML y actionlint locales, más ejecución real del
script de checks. No se despachó Actions ni Release para probar estos cambios. El ahorro esperado
proviene de eliminar ejecuciones automáticas y trabajo duplicado; no se ha medido en una factura.

Referencias: [sintaxis oficial de workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax),
[caché de setup-uv](https://github.com/astral-sh/setup-uv) y [release](release-workflow.md).
