# VERIDRA — contexto operativo

## GUARDRAILS
- Responder en español, breve y claro; priorizar resultados, cifras, rutas y acciones sobre prosa.
- Al iniciar un chat: leer este archivo desde GitHub y verificar rama, último commit y CI antes de trabajar.
- «Continúa» = ejecutar la siguiente tarea pendiente, no limitarse a proponerla.
- Trabajar con autonomía: investigar, editar, probar y corregir; preguntar solo por decisiones de riesgo o datos indispensables.
- Nunca afirmar que algo está probado sin evidencia. Diferenciar CI sintético de validación real en TRON.
- No exponer datos de clientes, secretos ni bases SQLite en chats, informes o commits.
- No eliminar datos históricos, activar cobros reales ni fusionar en main sin autorización explícita.
- Tras cambios relevantes: actualizar STATE de este archivo, con información verificable, y comunicar solo resultado, pruebas y bloqueo.
- Mantener este archivo conciso (objetivo <= 60 líneas); sustituir estado obsoleto, no acumular diario ni duplicar documentación.

## PROJECT
- Objetivo: VERIDRA como herramienta comercial privada y local de Webify en Windows/TRON; no SaaS público.
- Conservar CRM, prospección, auditorías, informes, ciclo comercial y facturación a clientes.
- Repo: RafaelAlbaWebify/veridra. Trabajo en `refactor/webify-operator-only`; PR #399 en borrador; main intacta.
- Lanzador: `scripts/windows/veridra-commercial-local.ps1`; acciones start/open/stop/status/preflight/backup/recovery-test/data-audit.
- Datos locales: `%LOCALAPPDATA%\VeridraCommercial`; las copias y recuperaciones deben ser aisladas.
- Legacy: conservar estructuras de identidad/workspace y protección de vinculación Stripe histórica hasta aclarar compatibilidad; no confundir con facturación Webify.

## STATE
- GitHub verificado 2026-10-16: commit `4368d045`; CI Linux y Windows completado correctamente.
- TRON: backup y recuperación aislada de 85 archivos correctos; SQLite identity quick_check=ok.
- Inventario restaurado: 1 usuario, 1 tenant, 1 directorio tenant, 0 proyectos, 0 evaluaciones, 1 workspace histórico, 1 vinculación Stripe SaaS, 0 eventos de planes; sin warnings.
- Nuevo script `tools/webify_restored_runtime_smoke.py`: prueba ASGI sobre copia temporal de snapshot; todavía NO ejecutado en TRON.
- Última rama local conocida en TRON: `refactor/webify-operator-only`, commit `ad4efde`; directorio `infra/` sin seguimiento: no eliminar.
- NEXT: actualizar rama local con `git pull --ff-only` tras verificar el árbol de trabajo; ejecutar smoke sobre `%LOCALAPPDATA%\VeridraCommercial\recovery-test-20261015_200939` y revisar resultado.
- AFTER: verificar situación de vinculación Stripe histórica sin revelar secretos; decidir cierre de limpieza y aceptación de PR #399.
- No considerar operatividad real al 100 % ni fusionar main hasta pasar aceptación funcional en TRON y autorización.
