"""Mesaj birleştirme / burst coalesce (D1) — abone-başı kuyruk + tek worker."""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from config import CONFIG

log = logging.getLogger("otel_demo.coalesce")

ProcessFn = Callable[[str, str, list], None]

_queues: dict[str, list[str]] = {}
_active: dict[str, bool] = {}
_registry_lock = threading.Lock()

_EXECUTOR = ThreadPoolExecutor(
    max_workers=max(1, CONFIG.coalesce_pool_size),
    thread_name_prefix="coalesce",
)


def _initial_sec() -> float:
    return CONFIG.coalesce_initial_ms / 1000.0


def _straggler_sec() -> float:
    return CONFIG.coalesce_straggler_ms / 1000.0


def _drain_queue_locked(user_id: str) -> list[str]:
    q = _queues.get(user_id)
    if not q:
        return []
    items = q[:]
    q.clear()
    return items


def enqueue(
    user_id: str,
    platform: str,
    message: str,
    process_fn: ProcessFn,
    background_add=None,
) -> None:
    start_worker = False
    with _registry_lock:
        q = _queues.setdefault(user_id, [])
        q.append(message)
        n = len(q)
        if not _active.get(user_id):
            _active[user_id] = True
            start_worker = True

    if not start_worker:
        log.info("[coalesce] burst — kuyruğa eklendi (user=%s queue_len=%d)", user_id, n)
        return

    log.info("[coalesce] worker başlatılıyor (user=%s)", user_id)
    try:
        if background_add is not None:
            background_add(_worker, user_id, platform, process_fn)
        else:
            _EXECUTOR.submit(_worker, user_id, platform, process_fn)
    except Exception as e:
        log.exception("[coalesce] worker başlatılamadı user=%s: %s", user_id, e)
        with _registry_lock:
            _active[user_id] = False


def _worker(user_id: str, platform: str, process_fn: ProcessFn) -> None:
    max_iter = max(1, CONFIG.coalesce_max_iter)
    try:
        outer_iter = 0
        while outer_iter < max_iter:
            collected: list[str] = []
            gather_iter = 0
            while gather_iter < max_iter:
                wait = _initial_sec() if gather_iter == 0 else _straggler_sec()
                if wait > 0:
                    time.sleep(wait)
                with _registry_lock:
                    batch = _drain_queue_locked(user_id)
                if batch:
                    collected.extend(batch)
                    gather_iter += 1
                    continue
                if collected:
                    break
                gather_iter += 1

            if not collected:
                break

            if len(collected) > 1:
                log.info("[coalesce] birleştirildi user=%s total=%d", user_id, len(collected))

            try:
                process_fn(user_id, platform, collected)
            except Exception as e:
                log.exception("[coalesce] process_fn hata user=%s: %s", user_id, e)

            with _registry_lock:
                pending_after = bool(_queues.get(user_id))
            if not pending_after:
                break
            outer_iter += 1
    finally:
        _retire(user_id, platform, process_fn)


def _retire(user_id: str, platform: str, process_fn: ProcessFn) -> None:
    while True:
        with _registry_lock:
            leftover = _drain_queue_locked(user_id)
            if not leftover:
                _active.pop(user_id, None)
                _queues.pop(user_id, None)
                return
        try:
            process_fn(user_id, platform, leftover)
        except Exception as e:
            log.exception("[coalesce] emeklilik process_fn hata user=%s: %s", user_id, e)

