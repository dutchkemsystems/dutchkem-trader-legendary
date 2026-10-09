# ADR-003: Data Storage

## Status
Accepted

## Context
Data persistence was required for application state and user records.

## Decision
Storage is defined by the models and schemas present in the source tree.
Schema changes should be tracked through migration scripts committed alongside
the code that requires them.

## Consequences

### Positive
- Schema changes are reviewable in pull requests
- Rollback is possible via migration history

### Negative
- Requires disciplined migration practice
