"""Read-only, non-executing SMEAC Copilot grounded on AAR and Memgraph context."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Awaitable, Callable

from src.uservice.smeac.models.contract.schemas import (
    SmeacCitation,
    SmeacDraftData,
    SmeacDraftRequest,
)


class SmeacCopilot:
    """Strictly read-only Copilot assembling SMEAC drafts from supplied theater context."""

    def __init__(
        self,
        llm_synthesizer: Callable[..., Awaitable[dict[str, str]]] | None = None,
    ) -> None:
        self.llm_synthesizer = llm_synthesizer

    async def generate_draft(
        self,
        body: SmeacDraftRequest,
        *,
        threats_data: Any | None = None,
        targets_data: Any | None = None,
        aar_summary: Any | None = None,
        llm_synthesizer: Callable[..., Awaitable[dict[str, str]]] | None = None,
    ) -> tuple[SmeacDraftData, dict[str, Any]]:
        """Assemble grounded non-executing SMEAC draft via live Gemini synthesis."""
        project_id = body.project_id
        citations: list[SmeacCitation] = []
        threat_warnings: list[str] = []

        threats_desc: list[str] = []
        targets_desc: list[str] = []
        aar_desc = "No recent telemetry summary available."

        # 1. Ground draft in Threat & Target context provided by ThreatFacade
        if threats_data is not None:
            for tz in getattr(threats_data, "threats", []) or []:
                label = f"{tz.name} ({tz.threat_type}, severity={tz.severity}, radius={int(tz.radius_m)}m)"
                threats_desc.append(label)
                threat_warnings.append(f"Active threat: {label}")
                citations.append(
                    SmeacCitation(
                        source_type="threat_zone",
                        source_id=tz.threat_id,
                        label=tz.name,
                    )
                )

        if targets_data is not None:
            items = getattr(targets_data, "items", targets_data)
            if isinstance(items, list):
                for tgt in items[:5]:
                    if isinstance(tgt, dict):
                        tgt_id = str(tgt["target_id"])
                        c_class = str(tgt["canonical_class"])
                        obs_count = int(tgt.get("observation_count", 1))
                        last_lat = float(tgt["last_lat"])
                        last_lon = float(tgt["last_lon"])
                        status = str(tgt["status"])
                    else:
                        tgt_id = str(tgt.target_id)
                        c_class = str(tgt.canonical_class)
                        obs_count = int(tgt.observation_count)
                        last_lat = float(tgt.last_lat)
                        last_lon = float(tgt.last_lon)
                        status = str(tgt.status)

                    t_label = f"{c_class} x{obs_count} at ({last_lat:.4f}, {last_lon:.4f}) [{status}]"
                    targets_desc.append(t_label)
                    citations.append(
                        SmeacCitation(
                            source_type="target_entity",
                            source_id=tgt_id,
                            label=c_class,
                        )
                    )

        # 2. Ground draft in AAR summary provided by AnalyticsFacade
        if aar_summary is not None:
            rows = getattr(aar_summary, "rows", None) or []
            row = rows[0] if rows else {}
            aar_desc = (
                f"Parquet AAR for {project_id}: {row.get('total_events', 0)} events across "
                f"{row.get('unique_drones', 0)} drone(s), {row.get('detection_count', 0)} detection(s), "
                f"min_battery={row.get('min_battery_pct')}%"
            )
            citations.append(
                SmeacCitation(
                    source_type="aar_summary",
                    source_id=f"aar:{project_id}:summary",
                    label=aar_desc,
                )
            )

        # 3. Synthesize SMEAC text via Gemini LLM (no deterministic fallback)
        synthesizer = llm_synthesizer or self.llm_synthesizer
        if synthesizer is None:
            api_key = os.getenv("GEMINI_API_KEY", "").strip()
            if not api_key:
                raise RuntimeError("GEMINI_API_KEY environment variable is required for SMEAC Copilot synthesis.")
            synthesizer = self._synthesize_with_llm

        drafted = await asyncio.wait_for(
            synthesizer(
                project_id=project_id,
                commander_intent=body.commander_intent,
                threats_desc=threats_desc,
                targets_desc=targets_desc,
                aar_desc=aar_desc,
            ),
            timeout=15.0,
        )
        required_keys = ("situation", "mission", "execution", "admin_logistics", "command_signal")
        if not isinstance(drafted, dict) or any(not str(drafted.get(k, "")).strip() for k in required_keys):
            raise RuntimeError("Gemini SMEAC Copilot returned an incomplete SMEAC draft payload.")

        draft = SmeacDraftData(
            project_id=project_id,
            draft_only=True,
            status="draft",
            situation=str(drafted["situation"]),
            mission=str(drafted["mission"]),
            execution=str(drafted["execution"]),
            admin_logistics=str(drafted["admin_logistics"]),
            command_signal=str(drafted["command_signal"]),
            source_citations=citations,
            threat_warning_summary=threat_warnings,
        )
        return draft, {"copilot_engine": "gemini_rag"}

    async def _synthesize_with_llm(
        self,
        *,
        project_id: str,
        commander_intent: str,
        threats_desc: list[str],
        targets_desc: list[str],
        aar_desc: str,
    ) -> dict[str, str]:
        from google import genai  # type: ignore[attr-defined]

        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        prompt = (
            "Generate a concise non-executing 5-paragraph military SMEAC draft as strict JSON with keys: "
            "situation, mission, execution, admin_logistics, command_signal.\n"
            f"Theater: {project_id}\nIntent: {commander_intent}\n"
            f"Threats: {threats_desc}\nTargets: {targets_desc}\nAAR: {aar_desc}\n"
            "Ground all facts strictly in the provided context without inventing coordinates or units."
        )
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=os.getenv("GEMINI_COPILOT_MODEL", "gemini-2.5-flash"),
            contents=prompt,
        )
        text = getattr(response, "text", "") or "{}"
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start : end + 1])
        return {}
