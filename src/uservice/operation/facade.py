"""Temporal client facade — single point of access for workflow operations."""

import os
import uuid

from temporalio.client import Client

_client: Client | None = None


import asyncio
import logging

logger = logging.getLogger(__name__)

async def get_temporal_client() -> Client:
    """Return a cached Temporal client instance."""
    global _client
    if _client is None:
        target = os.getenv("TEMPORAL_URL")
        if not target:
            host = os.getenv("TEMPORAL_HOST")
            port = os.getenv("TEMPORAL_PORT", "7233")
            if host:
                target = f"{host}:{port}"
            else:
                
                target = "127.0.1.1:7233"
        try:
            _client = await asyncio.wait_for(Client.connect(target), timeout=3.0)
        except Exception as e:
            logger.warning("Could not connect to Temporal at %s (%s), trying fallbacks", target, e)
            for fallback in ["127.0.1.1:7233", "127.0.0.1:7233", "localhost:7233"]:
                if fallback == target:
                    continue
                try:
                    _client = await asyncio.wait_for(Client.connect(fallback), timeout=2.0)
                    logger.info("Connected to Temporal at fallback %s", fallback)
                    break
                except Exception:
                    continue
            if _client is None:
                raise RuntimeError("Could not connect to Temporal on any host")
    return _client


async def start_workflow(
    workflow_cls,
    arg,
    *,
    task_queue: str,
    workflow_id: str | None = None,
) -> str:
    """Start a Temporal workflow and return its workflow ID."""
    client = await get_temporal_client()
    wf_id = workflow_id or f"wf-{uuid.uuid4()}"
    await client.start_workflow(workflow_cls.run, arg, id=wf_id, task_queue=task_queue)
    return wf_id


async def signal_workflow(workflow_id: str, signal_name: str, arg=None) -> None:
    """Send a signal to a running Temporal workflow."""
    client = await get_temporal_client()
    handle = client.get_workflow_handle(workflow_id)
    await handle.signal(signal_name, arg)


async def query_workflow(workflow_id: str, query_name: str):
    """Query a running Temporal workflow for its current state."""
    client = await get_temporal_client()
    handle = client.get_workflow_handle(workflow_id)
    return await handle.query(query_name)
