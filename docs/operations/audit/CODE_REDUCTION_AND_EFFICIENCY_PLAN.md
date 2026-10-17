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

## Primera implementación — consolidación de duplicados (2026-10-17)

**Base de comparación:** contenido de los cinco módulos inmediatamente anterior a este lote en `refactor/webify-operator-only`; no son cifras de HEAD inicial ni del ZIP. Se conservaron las firmas públicas, y los tests se ejecutan en CI del commit de la rama.

| Cambio | Líneas productivas antes/después | Reducción |
|---|---:|---:|
| `review_intelligence_sampling_safe_cli.py`: usar utilidades de selección de `review_intelligence_hardened_cli.py` en vez de copias de `_first_text` y `_first_attribute` | 354 → 331 | **23** |
| Cuatro almacenes (`workspace_policy.py`, `workspace_members.py`, `customer_store.py`, `prospect.py`) comparten `atomic_file_write.py` en vez de repetir `_atomic_write` | 62 líneas menos en módulos antiguos | **62** |
| Nuevo módulo compartido `atomic_file_write.py` | 0 → 21 | **−21** |
| **Neto inicial de código productivo** | | **≈64 líneas menos** |

La comparación incluye los cambios de estilo de un salto de línea extra en dos módulos (por tanto la cifra neta exacta al HEAD final puede variar por 2). **No se afirma ninguna mejora de velocidad o memoria:** la primitiva de escritura usa exactamente el mismo mecanismo fsync y rename. Es un primer ahorro estructural y elimina 4 copias de una operación crítica.

Commits: `5e393947` (reviews), `db18833e` (primitiva), `4094ed9a`, `4712f34a`, `ecfe571f`, `3b17df41` (migración de stores). Prueba nueva `tests/test_atomic_file_write_shared.py` commit `9b848034` con creación, sustitución y fallo de rename sin alterar datos antiguos. **CI completa del último SHA pendiente de comprobación**.

**Análisis adicional del ZIP por AST exacto:** funciones duplicadas `_atomic_write` (4), `_trusted_origin` (3), `_project` (3), `_require_white_label` (2), `_preset_control` (2) y `_first_attribute` (2). Son candidatos a consolidación, **no prueba** de que su semántica se mantenga bajo todo entorno y todos los perfiles. Siguiente lote: reutilizar `_trusted_origin` y `_project` tras verificar responsabilidades/rutas y medir p50/p95 de Discovery en TRON.

## Ejecución — Lote de simplificación 01 (2026-10-17)

**Evidencia de estado actual HEAD:** la familia `review_intelligence` tiene cuatro módulos (CLI base, hardened, sampling-safe, acceptance). Ya existe composición entre variantes mediante imports de base; no deben etiquetarse como cuatro implementaciones enteramente duplicadas. `visual_outreach` tiene cuatro: base, strict, regulatory y hardened; regulatory invoca strict, y hardened invoca regulatory. **Eliminar esos wrappers sin conservar CLI/política rompería comportamiento**.

**Refactor aplicado y cuantificado sobre los módulos modificados:**
- `visual_outreach_evidence_cli.py`: unifica `_latest_audit_zip` y `_safe_stem` con la implementación existente de `visual_outreach_evidence_strict_cli.py`; **770 → 755 líneas físicas, -15 LOC**. Commit `20dfe21bb765ffbcb99c2b78eb72a84f5a6e8d41`.
- `visual_outreach_regulatory_cli.py`: elimina parsers duplicados `_text` y `_integer` y los importa de strict; **276 → 273 líneas, -3 LOC**. Commit `3582b8e8a6189f1aeb30aedef00b2632c8a47eac`.
- **Total neto en estos dos archivos: -18 LOC productivas; módulos retirados: 0; mejoras de latencia/memoria medidas: ninguna**. Este primer cambio prioriza equivalencia de comportamiento, no publicidad de grandes ahorros. No modifica límites regulatorios, navegación, rutas de salida ni evidencia guardada.
- Aceptación técnica: ejecutar las cuatro suites `test_visual_outreach_evidence_cli.py`, `test_visual_outreach_evidence_strict_cli.py`, `test_visual_outreach_regulatory_cli.py`, `test_visual_outreach_hardened_cli.py`; confirmar CI Linux y Windows en el último commit. **Estado al documentar: CI pendiente**, no declararlo validado todavía.

**Siguiente ahorro significativo:** (1) grafo real de entrypoints y referencias de las variantes, (2) comparación de la carga/transformación ZIP y rutas Playwright de base y strict antes de extraer un motor común, (3) medir costos de IO, (4) si resulta equivalente, centralizar sin suprimir capas de políticas `regulatory` y `hardened`. No contar movimiento de líneas como ahorro neto.

## Ejecución — Lote de simplificación 02 (2026-10-17)

**Rama:** `refactor/webify-operator-only`. Se verificó el contenido de los tres módulos en HEAD tras los commits; comparación contra los valores iniciales de este lote, no contra ZIP histórico:

| Código de producción | LOC antes | LOC ahora | Neto |
|---|---:|---:|---:|
| `visual_outreach_evidence_cli.py` | 770 | 680 | **-90** |
| `visual_outreach_evidence_strict_cli.py` | 488 | 493 | +5 |
| `visual_outreach_regulatory_cli.py` | 276 | 273 | -3 |
| **Total en estos tres archivos** | **1.534** | **1.446** | **-88 (-5,74%)** |

Se han consolidado: `BusinessAudit` y carga de `audit_ranking.json`; selección del ZIP más reciente; normalización de nombres; conversión de campos regulatorios; y política Playwright `_safe_routes` que aborta destinos no públicos. Se conservaron las comprobaciones propias de la CLI base (1–100 negocios y rechazo de lotes sin auditorías válidas), por lo que la consolidación no elimina esas salvaguardas. **No se ha suprimido ningún módulo ni se ha alterado un registro comercial**.

**Eficiencia de lectura ZIP:** `_load` en strict construye un índice de nombres de `assessments/` una sola vez en vez de buscar un prefijo recorriendo todos los nombres del archivo para cada negocio; de O(A × R) a O(A + R) para A entradas y R filas de ranking, conservando la primera coincidencia y el orden del ranking. Prueba sintética de *solo búsqueda de nombres* con A=2.000, R=200, mediana de 30 ejecuciones en entorno aislado: **4,63 ms → 0,13 ms (~35,6×)**. Esto **no es** un benchmark completo del CLI, navegador, descompresión o capturas, y no se debe presentar como velocidad de VERIDRA 35 veces mayor.

**Pruebas añadidas:** selección determinista de archivo ZIP por rango, descarte de rangos fallidos y conservación de la primera coincidencia; identidad de la política de navegación segura compartida. Commits centrales `0cc825bf`, `b6557a25`, `667fbe24`, `28ece1be`, `8d8ce1db`; correcciones tipado/estilo `38f0403e` y `8807451b`. Al registrar este apartado, **la CI del commit final seguía en ejecución**. No declarar estabilidad de Windows hasta verde.

**Siguiente reducción con sentido:** comparar reglas y flujo de negocio de las variantes strict/regulatory/hardened antes de unificar los motores de captura y comprobar los wrappers invocados por `pyproject.toml`, herramientas PowerShell y scripts de lanzamiento. Reducir LOC no debe romper admisión de evidencias, redacción regulatoria o protección SSRF.

**Ajuste posterior de compatibilidad del test:** `tests/test_visual_outreach_evidence_cli.py` importa la política compartida con el nombre legacy `_install_safe_route`. `mypy` exigió declarar ese alias expresamente en `visual_outreach_evidence_cli.py` (commit `f4c9f4cb8b5deadb046cf75cdb794c5eb45b3876`). Tras este ajuste el recuento actual verificado es **682+493+273 = 1.448 líneas frente a 1.534 iniciales: reducción neta -86 líneas (-5,61%)**, no -88. La cifra -88 anterior queda sustituida por esta nueva medición. CI final de este SHA pendiente.


### Decisión de compatibilidad basada en entrypoints
El `pyproject.toml` actual expone **`veridra-visual-outreach-evidence = veridra.visual_outreach_hardened_cli:main`** y **`veridra-review-intelligence = veridra.review_intelligence_sampling_safe_cli:main`**. También expone la aceptación de review intelligence. Las cadenas internas conservan `strict` → `regulatory` → `hardened` en visual y `base` → `hardened` → `sampling_safe` en reseñas. Por tanto, los nombres `base`, `strict` o `regulatory` no prueban que sean redundantes o eliminables: algunos son dependencias transitivas activas. **Próximo refactor de gran tamaño solo después de inventariar los parámetros, las políticas de publicación y los artefactos generados, con tests de equivalencia.**


**Verificación CI del código:** ejecución [39054196529](https://github.com/RafaelAlbaWebify/veridra/actions/runs/39054196529) sobre commit `bb783523`: job Linux `verify` **success** (incluyendo Ruff, mypy y pytest); el job `windows-portability` seguía ejecutándose en la comprobación. La prueba de aceptación real en TRON aún no se ha efectuado para este refactor.


## Ejecución — Lote 03: evitar navegador innecesario (2026-10-18)

**Hallazgo de eficiencia confirmado por código:** `visual_outreach_regulatory_cli._augment_rows` abría `sync_playwright()`, Chromium y un contexto incluso cuando no había ninguna evidencia `broken_link` válida (URL presente, status >= 400 y captura de origen). El trabajo que necesitaba navegador era cero.

**Cambio:** commit `9f077813961481315f8144c9b6baa10eea3b1221` precalcula la lista de candidatos e interrumpe con `(0,0)` cuando es vacía. Solo abre navegador si realmente hay enlaces rotos que se deban capturar. La comprobación regulatoria para enlaces válidos mantiene su mismo orden y su semántica. Test de regresión `65b3bf62f395f4b7e078b7d22da42fe521b62f7a` utiliza un lanzamiento prohibido para garantizar la ruta sin navegador.

**Ahorro medido:** el cuerpo del módulo pasó de **273 a 279 líneas** (+6, un intercambio deliberado de LOC por eliminación de trabajo). El número de lanzamientos Chromium de **esta fase regulatoria** pasa de **1 a 0 para lotes sin candidatos**; no significa que los otros dos pipelines strict/hardened dejen de abrir navegador. No se ha realizado todavía benchmark de latencia end-to-end ni prueba en el equipo TRON. Si hay candidatos, se mantiene un navegador y la operación normal.

**Balance de eficiencia frente a ahorro de código:** los anteriores lotes de consolidación sumaron alrededor de **64 + 86 = 150 líneas productivas netas eliminadas**, sujetas a verificar de nuevo sobre el mismo SHA si se agregan otros cambios. Este lote añade 6, por lo que el saldo de esas iniciativas es aproximadamente **-144 LOC**. Cifras de lotes y ámbitos diferentes; no expresarlas como reducción porcentual del repositorio completo.

**Validación pendiente:** comprobar CI del SHA que contiene la prueba y observar una ejecución sintética con candidatos para certificar el recorrido normal; no declarar aceleración en segundos sin cronometrar.


### Extensión lote 03 — Hardened evita Chromium sin evidencia (2026-10-18)

En la secuencia **strict → regulatory → hardened**, la fase `hardened` seguía abriendo otro Chromium aun cuando todas las filas tenían `evidence` vacío o ausente. Ahora conserva la normalización de `evidence=[]`, `screenshot_ready_count=0`, el manifiesto v4 y el ZIP de salida, pero omite el navegador cuando no hay ninguna evidencia que revalidar. Commits `83c1b469` (código) y `cb714984` (test de ZIP sintético con navegador prohibido).

**Efecto operativo condicionado:** cuando no hay capturas que verificar, en ambas fases `regulatory` y `hardened` se evitan **2 procesos Chromium adicionales**, no se evitan las tareas previas `strict`, no se ha medido todavía p50/p95 ni un ahorro de tiempo end-to-end. Esta optimización añade código para evitar trabajo; no se debe contabilizar como LOC eliminadas. El primer lote visual quitó ~86 líneas netas y el lote compartido anterior ~64, pero el balance acumulado final debe recalcularse en el mismo SHA incluyendo estos fast paths. **CI Linux y Windows sobre el SHA de la nueva prueba pendientes**.


## Ejecución — Lote 04: escritor atómico compartido (2026-10-18)

Se comprobó que `atomic_file_write.atomic_write` (ya presente y probado en el repositorio) ofrece la misma estrategia que cinco bloques duplicados: tempfile en el mismo directorio, `flush()`, `os.fsync()`, y `Path.replace()`. Se sustituyeron esos bloques en cuatro archivos sin cambiar el modelo JSON, la ubicación de almacenamiento, el ID de contenido ni el tratamiento de errores.

| Archivo productivo | LOC antes | LOC después | Ahorro neto |
|---|---:|---:|---:|
| `report_delivery.py` (incluye captura SMTP) | 180 | 159 | -21 |
| `identity_email_delivery.py` | 225 | 214 | -11 |
| `project_delivery.py` | 182 | 171 | -11 |
| `recurring_service.py` | 222 | 211 | -11 |
| **Total, cuatro módulos** | **809** | **755** | **-54 LOC** |

Commits `a626a20f`, `bd2ebe7e`, `952b3e62`, `82c2beef`. El helper compartido no cambia en este lote. Mantener pruebas de creación/sustitución y error de escritura, así como regresión de entrega SMTP/capturas y estados comerciales. **CI del commit final pendiente al redactar esta nota.** Este cambio reduce código y coste de mantenimiento, **no afirma mejorar la latencia de escritura**, ya que mantiene fsync y replace.

**Acumulado de iniciativas documentadas (aproximado, no total de LOC de HEAD):** lotes anteriores `-64` (estimación) + `-86` (medición) + fast paths visuales `+19` + consolidación actual `-54` = **~ -185 LOC de producción**. Es un balance de cambios en áreas diferentes, no un porcentaje exacto del repositorio. Las mejoras de arranque Chromium están condicionadas a ausencia de evidencia válida; no se extrapolan a todo el programa.
