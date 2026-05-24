# Bug Index

## High Severity
- [BUG-001-global-400-on-all-endpoints.md](BUG-001-global-400-on-all-endpoints.md) - Global 400 Bad Request due to TrustedHostMiddleware rejecting Host Header
- [BUG-002-network-inspect-attribute-error.md](BUG-002-network-inspect-attribute-error.md) - AttributeError in get_network due to wrong aiodocker method
- [BUG-003-watchtower-coroutine-not-awaited.md](BUG-003-watchtower-coroutine-not-awaited.md) - Unawaited coroutine in watchtower service triggers compose actions silently
- [BUG-004-missing-await-docker-containers-list.md](BUG-004-missing-await-docker-containers-list.md) - Unawaited coroutine in Docker containers list
- [BUG-005-rate-limiting-bypass-via-forwarded-for.md](BUG-005-rate-limiting-bypass-via-forwarded-for.md) - Rate-Limiting bypass potential via X-Forwarded-For
- [BUG-006-deploy-app-500.md](BUG-006-deploy-app-500.md) - 500 Internal Server Error in /api/apps/deploy

## Medium Severity
- [BUG-007-compose-read-idor.md](BUG-007-compose-read-idor.md) - IDOR in Compose Read Endpoints
- [BUG-008-write-image-type-error.md](BUG-008-write-image-type-error.md) - TypeError in write_image when image_name is missing/null
- [BUG-010-jwt-reuse.md](BUG-010-jwt-reuse.md) - JWT Reuse nach Logout
