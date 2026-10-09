# ADR-004: Deployment Strategy

## Status
Accepted

## Context
The application needs to be deployed reliably and repeatably.

## Decision
Deployment uses CI/CD. The Docker environment in this repository provides a
reproducible local equivalent of production. Deployment pipelines are defined
in `.github/workflows/`.

## Consequences

### Positive
- Parity between local and production environments
- Automated testing gates before deployment

### Negative
- Container build steps add CI time
