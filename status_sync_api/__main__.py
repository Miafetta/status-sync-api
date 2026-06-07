from __future__ import annotations

import uvicorn

from status_sync_api.config import load_config


def main() -> None:
    config = load_config()
    uvicorn.run(
        "status_sync_api.app:app",
        host=config.server.host,
        port=config.server.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
