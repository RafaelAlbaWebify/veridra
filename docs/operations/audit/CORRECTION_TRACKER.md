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
