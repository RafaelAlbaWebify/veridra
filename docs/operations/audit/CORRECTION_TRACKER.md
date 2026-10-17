# VERIDRA — Registro maestro de correcciones

**Fecha de apertura:** 2026-10-17  
**Rama de trabajo:** `refactor/webify-operator-only`  
**Alcance:** seguimiento de remediación de los hallazgos F01–F182 documentados en las auditorías de código. Los identificadores pueden representar defectos, riesgos por confirmar, controles positivos o posibles elementos legacy; **no todos requieren modificar código**.

> **Este documento es la referencia operativa para continuar corrigiendo VERIDRA entre chats.** Las auditorías contienen evidencia y análisis; este registro controla decisiones, cambios, validación y pendientes. El 100% de inventario de 243 módulos Python no equivale al 100% de remediación ni a aceptación operativa.

## Estados y criterios

- **Pendiente de reconciliación**: hallazgo derivado del ZIP; no contrastado con la rama actual.
- **Confirmado / pendiente de corrección**: reproducido o verificado en la revisión del código actual.
- **Implementado / validación pendiente**: cambio confirmado en rama y pruebas aún insuficientes.
- **Validado en CI**: pruebas automatizadas del SHA específico superadas; no implica aceptación en TRON.
- **Validado en TRON**: reproducido y aceptado en el equipo real con evidencia.
- **Cerrado — no procede**: riesgo descartado con evidencia, o control positivo/legacy conservado conscientemente.

Para cerrar una corrección registrar **ID, causa raíz, archivos, commit SHA, tests, resultado CI de ese commit, prueba real cuando aplique y posibles migraciones/rollback**. No reutilizar porcentajes de auditoría como porcentaje de arreglos.

## 1. Trabajo realizado

| ID | Área | Estado de corrección | Implementación | Validación disponible | Falta para cerrar |
|---|---|---|---|---|---|
| **F01** | Discovery / Chromium: falsa confirmación de arranque | **Implementado; aceptación TRON pendiente** | `assisted_browser_runner.py` envía `request_id="startup"` tras crear contexto y página; `assisted_browser_provider.py` exige acuse explícito. Commits `b237685524f6098b3da0549f7a8f608d3c5d7de3`, `c53989fc2e3a76165dd0f8af7cfb5a94b44d1617` | Pruebas focalizadas locales: 16 superadas; `tests/test_discovery_startup_handshake.py` añadido en `012a79120f97b2ea35c0b9b9fbe6a2abc6aaec4b`. GitHub job `verify` completado en verde en la ejecución 39047283465; su job Windows todavía estaba en curso durante la última comprobación. | Confirmar estado final de Windows para SHA actual; ejecutar aceptación real de Chromium/Maps en TRON, capturar causa si sigue cerrándose. No confundir inicio confirmado con página Maps funcional. |
| **F03** | Carrera de tubería rota | **Revisado, cierre no acreditado** | La versión actual de `assisted_browser_provider.py` captura `BrokenPipeError/OSError` al enviar, según la conciliación previa. | Revisión estática | Test de carrera y clasificación de fallo del proceso real. |
| **F04** | Fallo de navegación inicial | **Revisado, cierre no acreditado** | El runner actual controla fallo inicial y permite al operador recuperar la página. | Revisión estática | Test en Windows real con fallo de navegación y mensaje comprensible. |

**No hay todavía evidencia de que Discovery esté operativo en el PC del usuario.** No se han corregido ni cerrado otros hallazgos automáticamente.

## 2. Pendientes prioritarios, agrupados por causa raíz

| Grupo | IDs vinculados | Prioridad | Estado | Trabajo / criterio de aceptación |
|---|---|---|---|---|
| **R01 — Ciclo de vida Chromium/IPC** | F01, **F02**, F03, F04, **F05**, F09, F70, F125 | P0 para Discovery | **Parcialmente implementado** | Un solo lector propietario de stdout con límite de tamaño; invalidar sesión al timeout/EOF; distinguir errores de navegación recuperables frente a proceso muerto; cierre determinista y readiness real. Tests fallo al inicio/EOF/broken pipe/timeout/retry, y aceptación TRON. |
| **R02 — Integridad entre registros y eventos** | F11, F15, F18, F20, F23, F35, F41, F49, F57, F64, F78–F80, F119–F121, F142–F145 | P1 | Pendiente de conciliación | Definir operaciones duraderas/idempotentes: prospecto→actividad→cliente, lead→assessment→cuota, propuesta→cliente, proyecto→cliente. Fallos inyectados antes/después de cada escritura; recuperación sin duplicados; nunca perder acuerdos. |
| **R03 — No confundir corrupción con ausencia** | F12, F16, F17, F21, F30, F33, F39, F53, F58, F77, F83, F92, F94, F101, F124, F134, F140, F144, F149 | P1 | Pendiente de conciliación | Excepciones diferenciadas para not-found, parse/corrupt y fallo de E/S; no sobrescribir archivos dañados ni devolver 404 engañosos; mostrar diagnóstico al operador y conservar copia/evidencia. |
| **R04 — Concurrencia, identidad y referencias** | F14, F22, F28, F31, F34, F36, F59, F61, F90–F93, F97–F100, F121–F122, F135 | P1 | Pendiente de conciliación | IDs inmutables, revisiones optimistas o bloqueo real interproceso, referencias de cliente/proyecto/perfil, migraciones reversibles. Pruebas con dos escritores y rollback. |
| **R05 — Envíos SMTP/webhook y ledger** | F41, F42, F45, F52, F54, F56, F72, F73, F80–F81 | P1 | Pendiente de conciliación | Grabar intento **antes** de enviar; idempotency key, estados queued/sent/failed/unknown, recuperación ante caída después de aceptación SMTP/HTTP. Distinguir aceptación del proveedor de entrega real. |
| **R06 — Seguridad y límites de rutas** | F06, F25–F27, F32, F37, F50, F65–F66, F74, F82, F107, F113, F116, F136, F147–F148 | P1 según exposición | Pendiente de conciliación | URL/host parsing estricto; IDs como tokens seguros; auth y misma procedencia; retención con revalidación en ejecución; rechazo de rutas expuestas sin evidencia. Tests de límites sin afectar datos. |
| **R07 — Limpieza legacy documentada** | F24, F38, F63, F70–F71, F75, F84–F89, F104, F106, F110, F133, F141, F150–F154 y candidatos adicionales de lotes 23–26 | P2 | Pendiente de análisis de referencias | Grafo de entrypoints por perfil (operator, local agency, CLI, tests), contratos de backup/migración, impacto en historial Stripe/cliente, retirada gradual con tests; **no borrar por ausencia de imports**. |
| **R08 — Calidad y trazabilidad de evidencia** | F07–F08, F40, F55, F67–F69, F95, F108–F112, F114–F118, F123, F126–F132 | P2 | Pendiente de conciliación | Menos falsos positivos, límites honestos de robots/DNS/accesibilidad, estadísticas de errores de importación, nombres de artefactos no colisionables y diagnósticos legibles. |

Los grupos **no son ocho bugs**: agrupan hallazgos interrelacionados con solapamientos deliberados. Los detalles específicos de F01–F182 permanecen en `batch-01...` a `batch-26...` y `functional-risk-reconciliation-2026-10-17.md`; ese documento de consolidación no sustituye este registro de ejecución.

## 3. Próximo lote de implementación sugerido

1. **R01 — terminar F02 y F05** y pruebas de regresión F01/F03/F04 en rama actual. Evitar modificaciones que solo silencien errores.
2. **Validación completa de CI Windows y TRON** para Discovery, con artefacto de diagnóstico y decisión go/no-go.
3. **R03 — introducir distinción uniforme entre ausencia/corrupción** en un store compartido piloto, con pruebas de no sobrescritura y migración no destructiva.
4. **R02 + R05 — plan transaccional común** de estados/idempotencia antes de tocar los flujos comerciales.
5. Revisar dependencias legacy solo después de estabilizar operaciones reales.

## 4. Protocolo de continuidad

Al abrir nuevo chat, consultar **primero este archivo**, seguido del índice `docs/operations/functional-code-audit-2026-10-17.md`, los lotes relevantes y la rama actual. Verificar commits y último estado CI, sin confiar en resultados antiguos. Cada cambio debe actualizar aquí el estado de su(s) ID(s), tests y commit, **en la misma tanda**. Mantener separado: **identificado / reproducido / implementado / CI validado / aceptado en TRON**. No afirmar un % de remediación sin contar unidades de corrección cerradas.

**Política de conservación:** ningún cambio sobre datos comerciales reales, Stripe histórico, `main`, borrados o migraciones destructivas sin plan de recuperación y autorización explícita.

## Lote de correcciones 02 — 2026-10-17: IPC y estado del navegador

**R01 / F02 — Implementado; CI del último commit y TRON pendientes.**
- `src/veridra/assisted_browser_provider.py`, commit `f45ecc9827b2604c925f4f721b71b1ca76fec333`: ante timeout, EOF o respuesta con protocolo incorrecto, descarta/termina el proceso hijo y sus pipes. No reutiliza un `stdout` cuyo lector en segundo plano podría consumir la respuesta de otra petición. También detiene el proceso tras BrokenPipe al escribir. Conserva excepciones del navegador recibidas en una respuesta válida como errores que no necesariamente requieren detenerlo.
- Limitación: aún usa un hilo de lectura por solicitud, pero la sesión se destruye en timeout; falta una prueba de hilos vivos/reinicio con procesos reales y cotas de lectura para F09.

**R01 / F05 — Implementado; CI del último commit y TRON pendientes.**
- `src/veridra/assisted_discovery.py`, commit `372e439362961ac47de215107eb8dc9ac60ff049`: los errores de canal `VisibleBrowserUnavailable` y `BrowserProtocolError` llevan a estado `failed` y se detiene el proveedor. Los errores recuperables generales siguen en `ready` conforme al contrato probado previamente.
- Riesgo residual: la distinción se basa en tipos de excepción; revisar todas las clases y la capa web para asegurar que el operador recibe un mensaje y una opción de reinicio.

**Pruebas y corrección de CI:**
- `tests/test_discovery_transport_failure.py` commit `47bcdc6664e85322332b538a517755fc94236d56`: comprueba la transición terminal tras caída del navegador y que un timeout invalida el proceso. El primer intento falló *strict mypy* por dos anotaciones ausentes, no por un fallo funcional conocido. Corregido en `d6f2bb74896523c801e49d0648eb2fabc3dac735`.
- **No cerrar F02/F05** hasta que el CI en `d6f2bb...` esté verde y se confirme su ejecución real cuando corresponda.
- Siguientes: F09 límite de lectura por línea, F06 URL origin, y primer piloto R03 de corrupción≠ausencia.

### Ampliación lote 02 — F06 (origen de Google Maps)
- **F06 implementado, CI/aceptación pendiente:** `src/veridra/assisted_google_maps.py` commit `0efc725f47c139dba5d008f72abd79a5e1b96340`. La página debe tener esquema HTTPS, origen de Google conocido y ruta real `/maps` o `/maps/...`; ya no se confía en las cadenas sueltas `google.` y `/maps` dentro de toda la URL. `tests/test_discovery_maps_origin.py` commit `948f3758433a21272f6da970eb9a6b86e7decee6` añade casos válidos y suplantaciones.
- **Limitación:** política inicial de dominios incluye `.com`, `.es`, `.co.uk`, `.fr`, `.de`, `.it`, `.pt`, `.ie`; si un usuario opera con otro dominio nacional oficial, ampliar whitelist y pruebas conscientemente. No cerrar hasta comprobar GitHub CI.

### Ampliación lote 02 — F09 (tamaño del mensaje IPC)
- **F09 implementado, CI pendiente.** `assisted_browser_provider.py` limita `readline(MAX_MESSAGE_BYTES + 1)`, rechazando la línea demasiado larga o truncada antes de decodificarla. Mantiene la distinción de EOF limpio frente a línea inválida. Commits `3e9ee8a50ca7fc3c7f635505b85695dacc7b6950`, `fa7dbfe7ce80c8e4d65c053a93b890b7247690fd`. Test `test_oversized_ipc_line_is_rejected_before_json_decode` en `fd2d537d84339d9ba8717d6489905a82b7290e5b`.
- **Correcciones de tipos de pruebas:** GitHub CI en un SHA intermedio encontró incompatibilidad del `BrokenProvider` de pruebas con `AssistedDiscoveryProvider`. Se ha corregido la anotación `TraversalResult` en `e5ff6730dc1d88621322c902e4cc7bdcb9c40056`. Esperar CI del SHA que incluye esta corrección, no usar un build anterior como prueba.
- Todavía no se valida Chromium en TRON; F01/F02/F05/F06/F09 deben mantenerse diferenciados entre **implementado**, **CI aprobado** y **aceptación real**.

## Lote de correcciones 03 — Piloto R03: corrupción de registros comerciales (F134)

- **F134 implementado, pendiente de CI y pruebas de inyección específicas.** `RecurringServiceStore.load()` ahora diferencia `RecurringServiceNotFound` (solo `FileNotFoundError`) de `RecurringServiceStoreError` (archivo corrupto / ilegible). `TenantRecurringServiceStore.load_or_empty()` crea borrador únicamente si el archivo realmente no existe; si está corrupto interrumpe con `TenantRecurringServiceStoreError`, sin sobrescribir evidencia. Commits: `99b99a1369ed9e1203de6ad566ff48690ab01893`, `9dc57bd7d94115d22fd57b44b63bfdc58359e215`.
- Prueba focalizada añadida a `tests/test_recurring_service.py` (`82fd7f1e68f8b383f7f6b3887c2b366db462daa7`): diferencia not-found/corrupt y verifica bytes preservados. Aún falta probar endpoint UI de corrupción, concurrencia y check in Windows.
- **No extrapolar este arreglo al resto de stores** hasta revisar cada caller y mantener contratos de error compatibles. R03 sigue abierto globalmente. En particular F20/F30/F58/F83/F140/F144 permanecen pendientes.


## Recuento de remediación — 17 octubre 2026

| Medida | Cantidad |
|---|---:|
| IDs registrados por auditoría F01–F182 | 182 |
| IDs con corrección incorporada en código | 7 |
| IDs sin una corrección incorporada | 175 |
| IDs cerrados con aceptación operativa registrada | 0 |

**IDs con corrección incorporada:** F01, F02, F05, F06, F09, F20 y F134. Los seis primeros de esta secuencia anteriores a F20 están incluidos en el commit 30e55ec7 con CI verde. F20 sigue pendiente de CI en su commit final.

**F20:** el almacenamiento de clientes distingue archivo ausente de archivo ilegible o inválido, y el conversor evita tratar el segundo caso como un nuevo cliente. Commits: 72612047, d0e989b8 y ef15fc29. Pendiente de pruebas focalizadas adicionales y verificación CI.

**Criterio:** 7/182 (3,85 %) se refiere a entradas con cambio de código; NO es porcentaje de funcionalidad operativa ni de errores solucionados definitivamente. Los 175 restantes incluyen también candidatos legacy, observaciones y riesgos que pueden no requerir un arreglo. Para calcular la cantidad real de correcciones necesarias habrá que clasificar los 182 IDs.


## Lote 04 — 2026-10-17: recuperación segura de delivery y prospectos

- **F30 — implementado; CI final pendiente.** `project_delivery.py` distingue `ProjectDeliveryNotFound` de almacenamiento ilegible/inválido; `tenant_project_delivery_store.py` solo inicializa registros vacíos ante ausencia real, propagando daños como `TenantProjectDeliveryStoreError`. Commits `6b783e59` y `8c21d286`. No se tocaron registros reales.
- **F17 — implementado; CI final pendiente.** `prospect.py` distingue `ProspectNotFound` de un registro corrupto; `tenant_prospect_store.py` propaga `TenantProspectNotFound`; `prospect_ingest.py` crea nuevo prospecto **solo** ante ausencia real, no si el existente falla al cargarse. Commits `70db2fc9`, `a6a7ccfd`, `775752e7`. Necesita pruebas focalizadas con JSON dañado y verificación de otros callers que capturan excepciones generales.
- **F20 — corregido el bloqueo Ruff de la rama** en `c3c40eb6`; CI del nuevo SHA pendiente de comprobar. Las ejecuciones intermedias no deben marcarse como éxito.
- **Recuento actualizado:** **9/182** entradas con cambio de código: F01, F02, F05, F06, F09, F17, F20, F30, F134. **173/182** sin cambio registrado. **0** cierres de aceptación integral acreditados. Los 173 restantes incluyen hallazgos que quizá no requieren cambio (riesgo, control positivo, código legacy). Porcentaje de entradas *abordadas*: **4,95%**. No es porcentaje de bugs efectivamente resueltos ni de operatividad.
- **Pendientes próximos:** pruebas de inyección/compatibilidad de F17/F30/F20; revisar llamadas UI que capturan `TenantProspectStoreError` de forma amplia; priorizar F58/F83/F140; posteriormente controlar concurrencia y side effects.

## Nueva prioridad: reducción de código y eficiencia

El objetivo principal del operador es simplificar el producto, retirar implementaciones redundantes y mejorar tiempos/consumo. Consultar [CODE_REDUCTION_AND_EFFICIENCY_PLAN.md](CODE_REDUCTION_AND_EFFICIENCY_PLAN.md) antes de iniciar nuevos lotes. Los F críticos de integridad y seguridad mantienen su carácter de bloqueantes; el resto debe agruparse en refactors basados en medición y no en microparches independientes. **No atribuir ahorro de líneas, rendimiento ni código muerto sin medir HEAD y entrada real.**

## Lote de simplificación 01 — 2026-10-17

**Objetivo principal actualizado:** reducción real de código y complejidad, con equivalencia funcional y benchmarks antes/después. La referencia detallada de línea base y candidatos está en [CODE_REDUCTION_AND_EFFICIENCY_PLAN.md](CODE_REDUCTION_AND_EFFICIENCY_PLAN.md).

- **RI-01 — Completa la implementación, aceptación final pendiente.** `review_intelligence_sampling_safe_cli.py` ya reutiliza las dos rutinas de selección de DOM de la variante hardened (commit `5e393947`), eliminando 23 líneas productivas netas. Requiere tests completos y, para una captura real, aceptación con navegador. No cambia esquema de evidencias ni los límites de muestreo. El job Linux `verify` en ejecución 39051287958 finalizó verde; Windows estaba en curso durante la comprobación.
- **STORE-01 — Implementada, CI final pendiente.** Cuatro almacenes comparten ahora `atomic_file_write.atomic_write`, idéntica semántica de creación, fsync y sustitución. Se eliminan aproximadamente 40 líneas netas adicionales contando el nuevo módulo. Commits `db18833e`, `4094ed9a`, `4712f34a`, `ecfe571f`, `3b17df41` y ajustes de estilo. Nueva prueba de creación/reemplazo y conservación del registro ante fallo `9b848034`.
- **Indicador acumulado de simplificación de este lote: ~64 líneas productivas netas retiradas, 4 implementaciones redundantes suprimidas y dos rutinas reutilizadas.** El número deberá recalcularse contra el SHA final si hay más commits. **Rendimiento: no medido / no afirmado.** Ni líneas eliminadas ni nuevo fichero implican automáticamente menor latencia.
- **Inventario de F01–F182:** no cambia el recuento de 9 IDs con fixes implementados, porque estos refactors son consolidaciones técnicas y no cierran automáticamente un hallazgo. Mantener dos indicadores diferenciados: reducción neta de código y remediación funcional.


## Refactor de eficiencia — lote visual 2026-10-17
El trabajo prioritario **no añade IDs F cerrados**: es simplificación medible, separada del recuento de remediación (9/182 implementados en el último recuento). Consultar [CODE_REDUCTION_AND_EFFICIENCY_PLAN.md](CODE_REDUCTION_AND_EFFICIENCY_PLAN.md), lote 02: **-88 líneas de producción netas en tres módulos** (1.534→1.446), mantenimiento de rutas públicas existentes, loader ZIP compartido y lectura optimizada. Pruebas nuevas para primera coincidencia/orden y política SSRF compartida. Los wrappers `strict`, `regulatory`, `hardened` y `sampling_safe` conservan funciones y contratos diferentes; NO borrar sin evidencia de uso. Validación GitHub del HEAD específico sigue siendo la puerta de aceptación; aún no hay resultado de TRON ni benchmark completo de Playwright.

## Refactor visual — lote 03 (2026-10-18)

Se ha optimizado `visual_outreach_regulatory_cli._augment_rows` para no iniciar Chromium cuando no existe ningún enlace roto con evidencia y estado HTTP >=400. Es una **mejora de eficiencia**, no un nuevo ID F cerrado ni una reducción de LOC. Commit `9f077813`; pruebas `65b3bf62` (sin candidatos, Chromium prohibido) y `971d75ec` (con candidatos, mantiene captura y contexto regulatorio). La función pasó de 273 a 279 LOC (+6). CI para el último commit pendiente. Consultar `CODE_REDUCTION_AND_EFFICIENCY_PLAN.md` para ahorro neto anterior y límites de la medición. Sin aceptación TRON.
