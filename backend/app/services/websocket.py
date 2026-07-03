"""
WebSocket Connection Manager — real-time pipeline events for HireFlow.

HR dashboard connects via WS /ws/{company_id}/{campaign_id} and receives
all pipeline events instantly as agents complete their work.

Event format (always):
  {
    "event":     "event.name",       # e.g. "pipeline.started"
    "payload":   { ... },            # event-specific data
    "timestamp": "2024-01-01T..."    # UTC ISO format
  }

Event catalogue:
  pipeline.started          — campaign pipeline has begun
  pipeline.completed        — all stages done, candidates selected
  pipeline.error            — unrecoverable error occurred

  checkpoint.pending        — HR approval needed (pipeline paused)
  checkpoint.approved       — HR approved, pipeline resuming
  checkpoint.rejected       — HR rejected, rollback executing
  checkpoint.revision       — HR requested revision, re-running agent

  agent.started             — an agent node has begun processing
  agent.completed           — an agent node finished successfully
  agent.failed              — an agent node encountered an error

  outreach.sent             — college outreach email sent
  candidate.registered      — new candidate registered
  candidate.shortlisted     — candidate passed resume screening
  interview.scheduled       — interview session scheduled
  offer.sent                — offer letter sent to candidate
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages all active WebSocket connections.

    Connections are keyed by (company_id, campaign_id) so we can
    broadcast to all HR users watching a specific campaign.

    A single company_id can have multiple campaign_id connections.
    A single campaign_id can have multiple WebSocket connections
    (e.g. multiple browser tabs).
    """

    def __init__(self):
        # { company_id: { campaign_id: [WebSocket, ...] } }
        self._connections: dict[str, dict[str, list[WebSocket]]] = {}

    # ── Connection lifecycle ──────────────────────────────────────────────────

    async def connect(
        self,
        websocket: WebSocket,
        company_id: str,
        campaign_id: str,
    ) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()

        if company_id not in self._connections:
            self._connections[company_id] = {}

        if campaign_id not in self._connections[company_id]:
            self._connections[company_id][campaign_id] = []

        self._connections[company_id][campaign_id].append(websocket)

        active = len(self._connections[company_id][campaign_id])
        logger.info(
            f"[WS] Connected — company={company_id}, campaign={campaign_id}, "
            f"active_connections={active}"
        )

        # Send welcome event to confirm connection
        await self._send_to_socket(
            websocket=websocket,
            event="connection.established",
            payload={
                "company_id": company_id,
                "campaign_id": campaign_id,
                "message": "Connected to HireFlow pipeline events",
            },
        )

    def disconnect(
        self,
        websocket: WebSocket,
        company_id: str,
        campaign_id: str,
    ) -> None:
        """Remove a WebSocket connection on disconnect."""
        try:
            if (
                company_id in self._connections
                and campaign_id in self._connections[company_id]
            ):
                conns = self._connections[company_id][campaign_id]
                if websocket in conns:
                    conns.remove(websocket)

                # Clean up empty lists
                if not conns:
                    del self._connections[company_id][campaign_id]
                if not self._connections[company_id]:
                    del self._connections[company_id]

            logger.info(
                f"[WS] Disconnected — company={company_id}, campaign={campaign_id}"
            )
        except Exception as e:
            logger.warning(f"[WS] Error during disconnect cleanup: {e}")

    # ── Sending events ────────────────────────────────────────────────────────

    async def send_event(
        self,
        company_id: str,
        campaign_id: str,
        event: str,
        payload: dict[str, Any],
    ) -> int:
        """
        Broadcast an event to ALL connections watching this campaign.

        Returns number of connections the event was sent to.
        Silently removes dead connections.
        """
        if (
            company_id not in self._connections
            or campaign_id not in self._connections[company_id]
        ):
            logger.debug(
                f"[WS] No active connections for company={company_id}, "
                f"campaign={campaign_id} — event '{event}' dropped"
            )
            return 0

        connections = self._connections[company_id][campaign_id].copy()
        dead_connections = []
        sent_count = 0

        for websocket in connections:
            try:
                await self._send_to_socket(
                    websocket=websocket,
                    event=event,
                    payload=payload,
                )
                sent_count += 1
            except Exception as e:
                logger.warning(f"[WS] Failed to send to connection: {e}")
                dead_connections.append(websocket)

        # Clean up dead connections
        for dead in dead_connections:
            self.disconnect(dead, company_id, campaign_id)

        if sent_count > 0:
            logger.info(
                f"[WS] Event '{event}' sent to {sent_count} connection(s) "
                f"— company={company_id}, campaign={campaign_id}"
            )

        return sent_count

    async def send_to_company(
        self,
        company_id: str,
        event: str,
        payload: dict[str, Any],
    ) -> int:
        """Broadcast an event to ALL campaigns of a company."""
        if company_id not in self._connections:
            return 0

        total_sent = 0
        for campaign_id in list(self._connections[company_id].keys()):
            total_sent += await self.send_event(
                company_id=company_id,
                campaign_id=campaign_id,
                event=event,
                payload=payload,
            )
        return total_sent

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _send_to_socket(
        self,
        websocket: WebSocket,
        event: str,
        payload: dict[str, Any],
    ) -> None:
        """Send a single event to a single WebSocket connection."""
        message = {
            "event": event,
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await websocket.send_text(json.dumps(message))

    # ── Diagnostics ───────────────────────────────────────────────────────────

    def get_active_connections(self) -> dict:
        """Return count of active connections per company/campaign."""
        result = {}
        for company_id, campaigns in self._connections.items():
            result[company_id] = {
                campaign_id: len(conns)
                for campaign_id, conns in campaigns.items()
            }
        return result

    @property
    def total_connections(self) -> int:
        """Total active WebSocket connections across all companies."""
        return sum(
            len(conns)
            for campaigns in self._connections.values()
            for conns in campaigns.values()
        )


# ── Singleton instance — imported everywhere ──────────────────────────────────
# Usage: from app.services.websocket import ws_manager
# Then:  await ws_manager.send_event(company_id, campaign_id, "event.name", {...})

ws_manager = ConnectionManager()
