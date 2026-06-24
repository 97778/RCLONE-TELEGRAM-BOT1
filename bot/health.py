import logging
from aiohttp import web

logger = logging.getLogger(__name__)


async def _health(request):
    return web.json_response({"status": "ok"})


async def start_health_server(port: int):
    """Lightweight HTTP server so Koyeb has an HTTP health target."""
    app = web.Application()
    app.router.add_get("/", _health)
    app.router.add_get("/health", _health)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("Health check server listening on :%s", port)
    return runner
