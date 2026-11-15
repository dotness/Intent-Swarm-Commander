"""Memgraph openCypher async client with explicit unavailability detection."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from neo4j import AsyncGraphDatabase


class MemgraphUnavailableError(RuntimeError):
    """Raised when Memgraph Bolt connectivity fails or times out."""


class MemgraphClient:
    """Async openCypher client targeting Memgraph over Bolt."""

    SCHEMA_STATEMENTS = (
        "CREATE CONSTRAINT ON (p:TacticalProject) ASSERT p.project_id IS UNIQUE;",
        "CREATE CONSTRAINT ON (t:ThreatZone) ASSERT t.threat_id IS UNIQUE;",
        "CREATE INDEX ON :ThreatZone(project_id);",
        "CREATE INDEX ON :ThreatZone(active);",
        "CREATE CONSTRAINT ON (m:SwarmMission) ASSERT m.command_id IS UNIQUE;",
        "CREATE CONSTRAINT ON (d:DetectionEvent) ASSERT d.event_id IS UNIQUE;",
        "CREATE INDEX ON :DetectionEvent(project_id);",
        "CREATE CONSTRAINT ON (e:TargetEntity) ASSERT e.target_id IS UNIQUE;",
        "CREATE INDEX ON :TargetEntity(project_id);",
    )

    def __init__(
        self,
        bolt_uri: str | None = None,
        username: str | None = None,
        password: str | None = None,
        driver: Any = None,
        timeout_s: float = 3.0,
    ) -> None:
        self.bolt_uri = bolt_uri or os.getenv("MEMGRAPH_BOLT_URI", "bolt://localhost:7687")
        self.username = username if username is not None else os.getenv("MEMGRAPH_USER", "")
        self.password = password if password is not None else os.getenv("MEMGRAPH_PASSWORD", "")
        self.timeout_s = timeout_s
        self._driver = driver

    def _get_driver(self) -> Any:
        if self._driver is not None:
            return self._driver
        auth = (self.username, self.password) if self.username else None
        try:
            self._driver = AsyncGraphDatabase.driver(
                self.bolt_uri,
                auth=auth,
                connection_timeout=self.timeout_s,
            )
            return self._driver
        except Exception as exc:
            raise MemgraphUnavailableError(f"Failed to create Memgraph Bolt driver: {exc}") from exc

    async def execute_read(
        self,
        query: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a parameterized read-only Cypher query against Memgraph."""
        driver = self._get_driver()
        try:
            if hasattr(driver, "execute_read") and not hasattr(driver, "session"):
                return await asyncio.wait_for(driver.execute_read(query, params or {}), timeout=self.timeout_s)

            async def _run() -> list[dict[str, Any]]:
                async with driver.session() as session:
                    result = await session.run(query, params or {})
                    records = await result.data()
                    return list(records)

            return await asyncio.wait_for(_run(), timeout=self.timeout_s)
        except MemgraphUnavailableError:
            raise
        except Exception as exc:
            raise MemgraphUnavailableError(f"Memgraph read query failed: {exc}") from exc

    async def execute_write(
        self,
        query: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a parameterized mutating Cypher query against Memgraph."""
        driver = self._get_driver()
        try:
            if hasattr(driver, "execute_write") and not hasattr(driver, "session"):
                return await asyncio.wait_for(driver.execute_write(query, params or {}), timeout=self.timeout_s)

            async def _run() -> list[dict[str, Any]]:
                async with driver.session() as session:
                    result = await session.run(query, params or {})
                    records = await result.data()
                    return list(records)

            return await asyncio.wait_for(_run(), timeout=self.timeout_s)
        except MemgraphUnavailableError:
            raise
        except Exception as exc:
            raise MemgraphUnavailableError(f"Memgraph write query failed: {exc}") from exc

    async def ensure_schema(self) -> None:
        """Create idempotent graph constraints and property indexes in Memgraph."""
        for stmt in self.SCHEMA_STATEMENTS:
            await self.execute_write(stmt)

    async def ping(self) -> bool:
        """Verify active connectivity to Memgraph."""
        rows = await self.execute_read("RETURN 1 AS ok")
        return bool(rows)

    async def close(self) -> None:
        """Close underlying driver resources."""
        if self._driver is not None and hasattr(self._driver, "close"):
            res = self._driver.close()
            if asyncio.iscoroutine(res):
                await res
