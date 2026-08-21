"""Background Nexus DTD auto-update: check periodically, apply only on new version."""

from __future__ import annotations

import asyncio
import logging

from app.config import get_nexus_dtd_config

logger = logging.getLogger(__name__)

_stop_event: asyncio.Event | None = None
_task: asyncio.Task | None = None


async def check_and_apply_nexus_dtd_update() -> str:
    """Run one auto-update cycle. Returns a status string for tests/logging."""
    from app.api.routes import dtd as dtd_routes

    return await dtd_routes.auto_update_dtd_from_nexus()


async def _loop(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        cfg = get_nexus_dtd_config()
        if cfg is None or not cfg.auto_update:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=60.0)
            except TimeoutError:
                continue
            break

        try:
            status = await check_and_apply_nexus_dtd_update()
            if status not in {"skipped_same_version", "skipped_not_configured", "skipped_disabled"}:
                logger.info("Nexus DTD auto-update cycle: %s", status)
        except Exception:
            logger.exception("Nexus DTD auto-update cycle failed")

        interval = max(1, int(cfg.check_interval_minutes)) * 60
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except TimeoutError:
            continue


async def start_nexus_dtd_auto_update() -> None:
    """Start background auto-update task (idempotent)."""
    global _stop_event, _task

    cfg = get_nexus_dtd_config()
    if cfg is None or not cfg.auto_update:
        logger.info("Nexus DTD auto-update disabled or not configured")
        return

    if _task is not None and not _task.done():
        return

    _stop_event = asyncio.Event()
    if cfg.on_startup:
        try:
            status = await check_and_apply_nexus_dtd_update()
            logger.info("Nexus DTD auto-update on startup: %s", status)
        except Exception:
            logger.exception("Nexus DTD auto-update on startup failed")

    _task = asyncio.create_task(_loop(_stop_event), name="nexus-dtd-auto-update")
    logger.info(
        "Nexus DTD auto-update started [interval_minutes=%s]",
        cfg.check_interval_minutes,
    )


async def stop_nexus_dtd_auto_update() -> None:
    """Stop background auto-update task."""
    global _stop_event, _task

    if _stop_event is not None:
        _stop_event.set()
    if _task is not None:
        try:
            await asyncio.wait_for(asyncio.shield(_task), timeout=5.0)
        except (TimeoutError, asyncio.CancelledError):
            _task.cancel()
            try:
                await _task
            except asyncio.CancelledError:
                pass
        except Exception:
            logger.exception("Error while stopping Nexus DTD auto-update")
        _task = None
    _stop_event = None
