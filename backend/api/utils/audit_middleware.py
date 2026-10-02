"""Record successful mutations without storing request bodies or secrets."""
import logging

class MutationAuditMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") in {"GET", "HEAD", "OPTIONS"}:
            return await self.app(scope, receive, send)
        status = 500
        async def audited_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)
        await self.app(scope, receive, audited_send)
        username = scope.get("audit_user")
        if username and 200 <= status < 300:
            try:
                from api.db.database import SessionLocal
                from api.utils.audit import log_activity
                async with SessionLocal() as db:
                    await log_activity(db, username, "http." + scope["method"].lower(), scope.get("path"))
            except Exception:
                logging.getLogger(__name__).exception("Mutation audit failed")
