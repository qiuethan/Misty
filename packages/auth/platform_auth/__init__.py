"""Shared API-key auth for UTMIST platform services.

Pure leaf: depends only on fastapi/starlette/argon2 + stdlib. Never imports
service code. Wire it per-service via `build_auth(...)`.
"""
