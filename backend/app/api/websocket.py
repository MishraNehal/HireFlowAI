"""
WebSocket API — Real-time pipeline events for HR dashboard.

Two WebSocket endpoints:

1. WS /ws/{company_id}/{campaign_id}
   - HR dashboard connects here to receive pipeline events
   - All agents and checkpoint decisions stream events here
   - Auto-reconnect friendly (connection.established sent on connect)

2. WS /ws/interview/{session_id}  [Milestone 5]
   - Voice/video interview sessions
   - Deepgram STT + ElevenLabs TTS streaming

Event format:
  {
    "event":     "pipeline.started",
    "payload":   { ... },
    "timestamp": "2024-01-01T00:00:00+00:00"
  }
"""
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.websocket import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


# ─────────────────────────────────────────────────────────────────────────────
# WS 1 — Pipeline Events (HR Dashboard)
# ─────────────────────────────────────────────────────────────────────────────

@router.websocket("/ws/{company_id}/{campaign_id}")
async def pipeline_websocket(
    websocket: WebSocket,
    company_id: str,
    campaign_id: str,
):
    """
    HR dashboard connects here to receive real-time pipeline events.

    Usage (JavaScript):
      const ws = new WebSocket('ws://localhost:8000/ws/{company_id}/{campaign_id}');
      ws.onmessage = (e) => {
        const { event, payload, timestamp } = JSON.parse(e.data);
        console.log(event, payload);
      };

    Events received:
      connection.established  — confirmed connected
      pipeline.started        — campaign pipeline has begun
      pipeline.completed      — all stages done
      pipeline.error          — error occurred
      checkpoint.pending      — HR approval needed (pipeline paused)
      checkpoint.approved     — approved, resuming
      checkpoint.rejected     — rejected, rolling back
      checkpoint.revision     — revision requested, re-running agent
      agent.started           — agent node began
      agent.completed         — agent node finished
    """
    await ws_manager.connect(
        websocket=websocket,
        company_id=company_id,
        campaign_id=campaign_id,
    )

    try:
        # Keep connection alive — listen for client messages
        # Client can send ping messages to keep connection open
        while True:
            data = await websocket.receive_text()

            # Handle ping from client
            if data == "ping":
                import json
                from datetime import datetime, timezone
                await websocket.send_text(json.dumps({
                    "event": "pong",
                    "payload": {"status": "alive"},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }))
            else:
                logger.debug(f"[WS] Received from client: {data}")

    except WebSocketDisconnect:
        ws_manager.disconnect(
            websocket=websocket,
            company_id=company_id,
            campaign_id=campaign_id,
        )
        logger.info(f"[WS] Client disconnected — company={company_id}, campaign={campaign_id}")

    except Exception as e:
        logger.error(f"[WS] Unexpected error — company={company_id}: {e}")
        ws_manager.disconnect(
            websocket=websocket,
            company_id=company_id,
            campaign_id=campaign_id,
        )


# ─────────────────────────────────────────────────────────────────────────────
# WS 2 — Interview Session (Milestone 5 — placeholder kept working)
# ─────────────────────────────────────────────────────────────────────────────

@router.websocket("/ws/interview/{session_id}")
async def interview_websocket(
    session_id: str,
    websocket: WebSocket,
):
    """
    Voice/video interview WebSocket — Milestone 5.
    Deepgram STT + ElevenLabs TTS streaming will be wired here.
    Currently accepts connection and returns ack.
    """
    await websocket.accept()
    logger.info(f"[WS:Interview] Connected — session={session_id}")

    import json
    from datetime import datetime, timezone

    await websocket.send_text(json.dumps({
        "event": "interview.connected",
        "payload": {
            "session_id": session_id,
            "message": "Interview WebSocket connected — full implementation in Milestone 5",
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }))

    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(json.dumps({
                "event": "interview.ack",
                "payload": {"received": data},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }))
    except WebSocketDisconnect:
        logger.info(f"[WS:Interview] Disconnected — session={session_id}")


# ─────────────────────────────────────────────────────────────────────────────
# REST — WebSocket diagnostics (admin only)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/api/v1/ws/status")
def websocket_status():
    """
    Returns active WebSocket connection counts.
    Useful for debugging — how many HR dashboards are connected.
    """
    return {
        "success": True,
        "data": {
            "total_connections": ws_manager.total_connections,
            "connections_by_campaign": ws_manager.get_active_connections(),
        },
    }