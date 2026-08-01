"""Make this service's own log records actually reach the logs.

uvicorn configures only its `uvicorn*` loggers and leaves the ROOT logger with
no handler at all. A module logger (`logging.getLogger(__name__)`) therefore
finds no handler anywhere up its chain and falls through to
`logging.lastResort`, which emits WARNING and above and silently drops
everything below it.

That is not theoretical. The single-instance note this service logs at startup
never appeared once in Railway's logs -- five lines, all of them uvicorn's own.

Most of this service dodged it by accident: sessions.py, transcribe.py and the
meetings router all log to ``meeting.audit``, which platform_auth's audit
middleware configures with its own stdout handler at INFO. Loggers OUTSIDE that
name -- src.api.app, src.pipeline.minutes -- had nothing. This closes the gap
for the whole ``src`` package rather than pushing every module onto the audit
logger, which is named for something else and owned by another package.
"""

import logging
import sys

# Every module in this service is imported as ``src.*``, so this one logger is
# the common ancestor of all of them.
_SERVICE_LOGGER = "src"

# Marks the handler as ours, so repeated create_app() calls (the test suite
# builds many) top up nothing and output is never doubled.
_HANDLER_TAG = "_meeting_service_handler"


def configure_logging(level: str = "INFO") -> None:
    """Attach a stdout handler to this service's logger namespace.

    Deliberately NOT the root logger: that would also switch on DEBUG/INFO for
    botocore, httpx and friends, which is a lot of noise for one startup line.
    Deliberately leaves ``propagate`` alone, so records still reach root and
    pytest's caplog keeps working.
    """
    logger = logging.getLogger(_SERVICE_LOGGER)
    logger.setLevel(level)

    if any(getattr(h, _HANDLER_TAG, False) for h in logger.handlers):
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    setattr(handler, _HANDLER_TAG, True)
    logger.addHandler(handler)
