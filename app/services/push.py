import logging

import httpx

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


async def send_push(token: str, title: str, body: str, data: dict | None = None) -> None:
    """Fire-and-forget a push through Expo's push service (free, no GCP/billing involvement).

    Never raises — a diner's order should never fail because a push couldn't be delivered (a
    stale/invalid token, the diner declined notification permission client-side but an order was
    still created some other way, network trouble, etc.). Errors are logged, not surfaced.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                EXPO_PUSH_URL,
                json={"to": token, "title": title, "body": body, "data": data or {}, "sound": "default"},
                headers={"Content-Type": "application/json"},
            )
            result = response.json()
            ticket = (result.get("data") or {}) if isinstance(result, dict) else {}
            if ticket.get("status") == "error":
                logger.warning("Expo push rejected for token %s: %s", token, ticket.get("message"))
    except Exception:
        logger.exception("Failed to send push notification")
