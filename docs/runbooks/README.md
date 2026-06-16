# Runbooks operativos

- [Backfill histórico](backfill.md): reprocesar un rango de meses desde Bronze
  hasta Gold con Dagster, dbt y asset checks.
- [Data Engineer](data-engineer.md): ejecutar, validar y comunicar
  reprocesamientos/backfills desde el rol técnico de implementación.
- [Data Owner](data-owner.md): decidir la aptitud del dato ante un bloqueo de
  calidad, analizar el impacto aguas abajo y delegar la remediación.
- [Deploy staging data](deploy-staging-data.md): levantar el stack completo
  de datos Phase-2 en staging (EC2 + Docker Compose + Traefik + TLS), poblar
  datos con Dagster y operar el ciclo de vida (snapshot / destroy / restore).
