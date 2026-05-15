import logging

import uvicorn

from src.bot.__main__ import main as bot_main

logging.basicConfig(level=logging.INFO)


def run_api():
    uvicorn.run(
        "src.api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "api":
        run_api()
    else:
        bot_main()
