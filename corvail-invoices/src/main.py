from typing import Optional
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.routes import router
from src.core import CorvailInvoicesError
from src.core.config import get_settings


def _configure_logging() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.getLogger("corvail.invoices").info(
        "[Corvail Invoices] API online. Model: %s. Environment: %s",
        settings.gemini_model,
        settings.environment,
    )
    yield


_configure_logging()
app = FastAPI(title="Corvail Invoices", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(CorvailInvoicesError)
async def corvail_error_handler(request: Request, exc: CorvailInvoicesError):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "error_code": exc.error_code,
            "message": exc.message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    logging.getLogger("corvail.invoices").error("Unhandled error", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "error_code": "internal_error",
            "message": "Unexpected error",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


app.include_router(router)
