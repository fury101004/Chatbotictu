from __future__ import annotations

import json
import logging
import os
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator


logger = logging.getLogger("trafilatura")


class ExtractRequest(BaseModel):
    url: str | None = Field(default=None, description="URL cần trích nội dung")
    html: str | None = Field(default=None, description="HTML thô nếu có sẵn")
    output_format: str = Field(default="txt", description="txt | json")

    @model_validator(mode="after")
    def validate_input(self) -> "ExtractRequest":
        url = (self.url or "").strip()
        html = (self.html or "").strip()
        if not url and not html:
            raise ValueError("Cần có 'url' hoặc 'html'.")
        if self.output_format not in {"json", "txt"}:
            raise ValueError("output_format phải là 'json' hoặc 'txt'.")
        if url and not url.lower().startswith(("http://", "https://")):
            raise ValueError("URL phải bắt đầu bằng http:// hoặc https://")
        return self


app = FastAPI(
    title="Trafilatura Extraction Service",
    version="1.0.0",
    description="Extract main webpage content for chatbot web search.",
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    detail = "; ".join(f"{item.get('loc', [])[-1]}: {item.get('msg', 'invalid')}" for item in errors) if errors else str(exc)
    logger.warning("Validation error on %s: %s", request.url.path, detail)
    return JSONResponse(status_code=422, content={"detail": detail, "errors": errors})


_TIMEOUT = float(os.getenv("TRAFILATURA_TIMEOUT_SECONDS", "20"))
_NO_SSL = os.getenv("TRAFILATURA_NO_SSL", "false").lower() == "true"
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _fetch_url(url: str) -> str | None:
    import requests

    try:
        response = requests.get(
            url,
            headers={"User-Agent": _BROWSER_UA},
            timeout=int(_TIMEOUT),
            verify=not _NO_SSL,
        )
        response.raise_for_status()
        if response.text and len(response.text) > 100:
            return response.text
    except Exception as exc:
        logger.debug("requests fetch failed: %s", exc)

    try:
        import trafilatura
    except Exception as exc:
        logger.warning("trafilatura is not installed or unavailable: %s", exc)
        return None

    downloaded = trafilatura.fetch_url(url, no_ssl=_NO_SSL, config=None)
    if downloaded:
        return downloaded
    if not _NO_SSL:
        return trafilatura.fetch_url(url, no_ssl=True, config=None)
    return None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/extract")
def extract(request: ExtractRequest) -> dict[str, Any]:
    try:
        import trafilatura
    except Exception as exc:
        logger.warning("trafilatura is not installed or unavailable: %s", exc)
        return {
            "success": False,
            "source": {"url": request.url},
            "data": {"text": ""},
            "error": "Chưa cài thư viện trafilatura cho extraction service.",
        }

    source_html = (request.html or "").strip() or None
    source_url = (request.url or "").strip() or None

    if not source_html and source_url:
        logger.info("Fetching URL: %s", source_url[:80] + "..." if len(source_url) > 80 else source_url)
        source_html = _fetch_url(source_url)
        if not source_html:
            return {
                "success": False,
                "source": {"url": source_url},
                "data": {"text": ""},
                "error": "Không tải được nội dung.",
            }

    if not source_html:
        return {"success": False, "source": {}, "data": {"text": ""}, "error": "Không có url hoặc html để trích."}

    extracted = trafilatura.extract(
        source_html,
        url=source_url,
        favor_precision=True,
        include_links=False,
        include_images=False,
        include_comments=False,
        output_format=request.output_format,
        target_language=os.getenv("TRAFILATURA_TARGET_LANGUAGE") or None,
        deduplicate=True,
        with_metadata=request.output_format == "json",
    )

    if not extracted:
        return {
            "success": False,
            "source": {"url": source_url},
            "data": {"text": ""},
            "error": "Trafilatura không trích được nội dung từ trang này.",
        }

    if request.output_format == "json":
        try:
            data = json.loads(extracted)
        except json.JSONDecodeError:
            data = {"raw": extracted}
    else:
        data = {"text": extracted}

    return {"success": True, "source": {"url": source_url}, "timeout_seconds": _TIMEOUT, "data": data}
