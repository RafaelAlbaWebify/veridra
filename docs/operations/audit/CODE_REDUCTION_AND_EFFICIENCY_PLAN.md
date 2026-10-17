# VERIDRA — Plan de simplificación y eficiencia

Fecha: 2026-10-17. Prioridad expresada por el operador: **reducir código y mejorar eficiencia sin perder funcionalidad ni evidencia comercial**.

## Línea base medida en el ZIP aportado
- `src/veridra/`: **243 módulos Python, 51.902 líneas físicas**; **35 archivos `*_cli.py`** y **46 `*_web.py`**.
- Mayores módulos: `agency_prospect_discovery_web.py` (1.438 líneas), `agency_prospect_web.py` (1.107), `reports.py` (873), `crawl.py` (794), `visual_outreach_evidence_cli.py` (769), `crawl_jobs.py` (718), `review_intelligence_hardened_cli.py` (554), `agency_project_customer_web.py` (551). Cifras **solo del ZIP**, no se ha medido todavía HEAD.
- Un archivo muy largo indica coste de mantenimiento, no necesariamente redundancia. **Dividir un archivo en cuatro no reduce líneas ni tiempo de ejecución**.
- La auditoría por módulos no demuestra que una ruta sea inaccesible desde CLI, pruebas, import dinámico o un launcher de Windows.

## Prioridades por retorno esperado

| Orden | Candidato | Hipótesis / evidencia | Verificaciones antes de cambiar | Objetivo |
|---|---|---|---|---|
| 1 | Múltiples pipelines de evidencia visual y review intelligence | `visual_outreach_evidence_cli.py`, variantes `_strict`, `_hardened`, `_regulatory`; `review_intelligence_cli.py` y variantes `_hardened`, `_sampling_safe`, `_acceptance` | Comparar AST/call graph, flags, escenarios y export contracts; confirmar cuál se usa en operación real | Una implementación central + políticas configurables y wrappers mínimos o supresión de wrappers probadamente obsoletos |
| 2 | Router legacy de monitorización y SaaS hosted | `monitoring_web.py` no montado en runtime estándar; otros `auth_api`, `browser_auth_web`, invitaciones y recuperación no montados en operador | Matriz runtime operator/local-agency/CLI/tests; historial, migraciones, backups y datos Stripe | Retirada gradual de código ejecutable no utilizado, con pruebas de rutas ausentes |
| 3 | Persistencia JSON repetida | Patrón save/load/list, error mapping, fsync/rename, locking repetido en customers/prospects/delivery/deals/profiles | Contratos de ID, atomicidad, owner, migraciones y errores de cada store | Biblioteca ligera probada para I/O atómico, error tipado y validación; evitar una abstracción genérica opaca |
| 4 | HTML/JS inline en routers extensos | UI y tablas/formularios repetidos en `agency_prospect_discovery_web.py` y `agency_prospect_web.py` | Inventario de DOM selectors, Playwright/UI tests y diferencias funcionales | Templates/fragmentos compartidos sin alterar navegación |
| 5 | Discovery: latencia y arranque | Lecturas por tarjeta, navegación de detalle secuencial, startup/timeouts, observaciones | Capturar distribución p50/p95 del tiempo, llamadas al navegador, throughput, % detail failures | Menos navegaciones, presupuestos de tiempo globales, caché explícita, no extrapolar a Maps real sin TRON |
| 6 | DB y jobs: escrituras | Repetición de consultas/listado, leases, eventos, export de evidencias | SQLite EXPLAIN QUERY PLAN, tamaño real de tablas, contención, IO | Índices solo si se justifican, batch transaction e idempotencia |

## Método: medir primero, retirar después
1. Obtener métricas **en HEAD**: módulos y LOC, rutas por perfil, import graph, scripts invocados, funciones repetidas y resultados de tests; guardar SHA.
2. Generar un **mapa de duplicación semántica**, no solo coincidencia textual. Marcar los candidatos como *seguro de retirar*, *necesita migración* o *activo/intencional*.
3. Elegir un piloto de pocas dependencias; realizar cambio en rama, pruebas, comparar LOC **netas** (implementación+tests, por separado) y benchmarks reproducibles (mediana/p95 tiempo; memoria; número de I/O y llamadas).
4. No eliminar funciones por parecer legacy sin evidencia de rutas/entrypoints en Windows. Conservar migraciones, compatibilidad de backups, acuerdos y logs.
5. Solo llamar *mejora de rendimiento* a una reducción cuantificada de latencia/carga/IO para el mismo resultado; menor LOC no implica mejor runtime.

## Métricas de éxito
- LOC productivas (sin tests) antes/después por área y total; archivos/módulos eliminados netos; clases/rutas duplicadas eliminadas.
- Pruebas y contratos conservados, CI Linux+Windows.
- p50/p95 de una captura de Discovery acotada; llamadas por negocio y ratio de perfiles enriquecidos.
- Duración de import de N prospectos sintéticos, coste I/O, duplicados y errores, sin datos comerciales.
- Tiempo de arranque del operador y tamaño del artefacto distribuido.

## Relación con CORRECTION_TRACKER.md
Este plan **reordena** el backlog por reducción de complejidad y rendimiento; no cierra ninguno de los F01–F182 automáticamente. La integridad de datos y seguridad son límites no negociables. Actualizar ambos documentos en cada lote con antes/después y pruebas.
