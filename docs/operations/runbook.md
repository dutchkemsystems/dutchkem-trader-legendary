# Operations Runbook

## Overview
This runbook covers common operational tasks for this service.

## Local development
1. Copy `.env.example` to `.env` and fill in required values.
2. Build and run: `docker compose up`.
3. The application listens on the port defined in the environment.

## Health check
- Application responds on its configured health endpoint.
- Logs are emitted to stdout.

## Deployment
- Deployment is triggered by CI on the main branch.
- Rollback: revert to the previous commit and push.

## Incident response
1. Confirm the issue via logs and metrics.
2. If a recent deploy is suspected, roll back first, investigate second.
3. Open an issue with a timeline once the incident is resolved.

## Contact
- Primary: dutchmondcomputers@gmail.com
