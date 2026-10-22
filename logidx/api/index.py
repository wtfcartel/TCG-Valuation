"""Vercel entry point: the whole dashboard and API as one Python function (ASGI app `app`)."""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from logidx.security import configure_logging, redact  # noqa: E402

configure_logging()


def _startup_error_app(reason: str):  # type: ignore[no-untyped-def]
    """Explain configuration problems instead of returning an opaque 500."""

    async def error_app(scope, receive, send):  # type: ignore[no-untyped-def]
        if scope["type"] != "http":
            return
        body = (
            f"LogiDx could not start.\n\n{reason}\n\n"
            "Check the environment variables in the Vercel project settings (see logidx/docs/03-deploy-vercel.md)."
        ).encode()
        headers = [(b"content-type", b"text/plain; charset=utf-8")]
        await send({"type": "http.response.start", "status": 503, "headers": headers})
        await send({"type": "http.response.body", "body": body})

    return error_app


def _build():  # type: ignore[no-untyped-def]
    try:
        from logidx.bootstrap import ensure_ready
        from logidx.web.app import create_app

        ensure_ready()  # migrate (advisory-locked), seed, first-user bootstrap
        return create_app(start_scheduler=False)
    except Exception as exc:
        logging.getLogger("logidx").exception("startup failed")
        return _startup_error_app(redact(f"{type(exc).__name__}: {exc}"))


app = _build()
