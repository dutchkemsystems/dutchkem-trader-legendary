# ADR-002: Technology Stack

## Status
Accepted

## Context
The project required a stack that supports rapid development, has strong
community support, and is deployable across environments.

## Decision
The chosen stack is documented in the repository root (see `requirements.txt`
or `package.json`). Selection criteria:

1. Mature ecosystem and long-term support
2. Compatibility with CI/CD and containerization
3. Availability of tooling for testing and linting

## Consequences

### Positive
- Well-supported toolchain
- Easy onboarding for contributors familiar with the stack

### Negative
- Some ecosystem lock-in
- Periodic dependency upgrades required
