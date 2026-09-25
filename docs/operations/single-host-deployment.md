# Optional Linux/cloud deployment bundle

Status: **NON-CANONICAL / OPTIONAL**

The `deployment/` Docker Compose + Caddy bundle is retained as a tested portability artifact for a possible future hosted VERIDRA architecture.

It is **not** the first-customer production model and is **not** required by #296.

## Canonical runtime

The canonical Webify Presence Care runtime is Rafael's Windows PC:
- private operator application;
- `127.0.0.1` only;
- no public DNS/TLS;
- no public reverse proxy;
- no VPS/PaaS;
- no direct customer access to VERIDRA.

See `docs/WINDOWS_LOCAL_OPERATIONS.md` and issue #296.

## Future use

If Webify later decides to make VERIDRA a directly hosted/customer-accessible service, this bundle can be reconsidered, but that requires a separate architecture decision and a new public-host security/deployment acceptance cycle.

Do not provision hosting or create paid infrastructure solely because these files exist.
