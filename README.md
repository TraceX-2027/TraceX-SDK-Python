# TraceX-SDK-Python

Official TraceX Python Client SDK (FastAPI, Flask & Django) - Crash Reporting, Breadcrumbs & Offline Buffer.

## Installation
Run: pip install -e ".[dev]"

## Quickstart
Import tracex and initialize it with your project_key, endpoint="https://api.tracex.io/api/v1/crashes", environment="production", app_version="1.0.0", and max_breadcrumbs=50, then call tracex.capture_exception(exc) inside your exception handler.

## Testing & Type Checking
Run: pytest and mypy src tests