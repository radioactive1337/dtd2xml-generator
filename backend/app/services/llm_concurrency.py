"""Process-wide limit on concurrent LLM requests, shared by all routes."""

from __future__ import annotations

import asyncio
import os

# Allow at most this many LLM requests to run concurrently across all users.
# Keeps the LLM backend responsive and prevents a single runaway client from
# starving everyone else.  Adjust via env var LLM_CONCURRENCY if needed.
LLM_CONCURRENCY = int(os.getenv("LLM_CONCURRENCY", "5"))
llm_semaphore = asyncio.Semaphore(LLM_CONCURRENCY)
