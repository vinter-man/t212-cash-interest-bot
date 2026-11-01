import asyncio
import logging

from cash_interest.bot.app import run
from cash_interest.config import Settings


def main() -> None:
    settings = Settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # httpx logs every request URL at INFO; the poller already says what it fetched and why.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    asyncio.run(run(settings))


if __name__ == "__main__":
    main()
