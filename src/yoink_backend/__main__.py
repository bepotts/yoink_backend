# Provides the installed command and python -m entry point.
"""Run the Yoink backend HTTP server."""

import uvicorn


# Starts the ASGI server on the interface exposed by Docker.
def main() -> None:
    """Serve the API on port 8000."""
    uvicorn.run("yoink_backend.app:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
