import base64
import json
import logging

import httpx
from google.auth.exceptions import DefaultCredentialsError
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.auth import default as google_auth_default
from pydantic import BaseModel, ValidationError

from app.core.config import settings

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-2.5-flash"

EXTRACTION_PROMPT = (
    "You are reading a photo of a restaurant menu (or a single menu page). Extract every distinct "
    "dish/drink you can clearly read. For each one, output an object with exactly these fields: "
    '"name" (object with "en" and "de" string keys, required — both, regardless of which language '
    'the menu is printed in: keep the original and translate for the other, or translate both if '
    'neither is EN/DE), "description" (same "en"/"de" object shape, empty strings if none is '
    'printed), "price" (number, the numeric price with no currency symbol, or null if you can\'t '
    "read one). Skip section headers (e.g. \"Starters\"), skip anything you can't read with "
    "reasonable confidence rather than guessing. Respond with ONLY a JSON array of these objects, "
    "no other text."
)


class MenuExtractionError(Exception):
    """Vertex AI call failed, or its response couldn't be parsed into usable items."""


class ExtractedMenuItem(BaseModel):
    # Matches MenuItem.name/description's existing per-language dict shape (app/models/menu.py) —
    # scoped to EN/DE only, same as the rest of the diner-facing language infra (TASKS.md,
    # 2026-09-18: "postpone the paid translation API... scoped to EN/DE only").
    name: dict[str, str]
    description: dict[str, str] = {}
    price: float | None = None


def _get_access_token() -> str:
    """Application Default Credentials — the Cloud Run service account's own identity in
    production, `gcloud auth application-default login` for local dev. Deliberately not lazily
    cached: token lifetime/refresh is exactly what google-auth's Credentials object already
    handles, re-deriving it per call keeps this function trivially correct."""
    credentials, _ = google_auth_default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    credentials.refresh(GoogleAuthRequest())
    return credentials.token


async def extract_menu_items_from_image(image_bytes: bytes, mime_type: str) -> list[ExtractedMenuItem]:
    """Calls Gemini 2.5 Flash via Vertex AI to pull structured items out of a menu photo.

    Unlike send_push, this DOES raise (MenuExtractionError) on failure — a restaurant uploading a
    photo needs to know extraction failed so they can retry or fall back to manual entry, not have
    it silently no-op. Never auto-commits anything to the menu; callers are expected to show the
    result for the restaurant to review/edit before creating real MenuItem rows.
    """
    if not settings.gcp_project_id:
        raise MenuExtractionError("Menu extraction isn't configured (no GCP project set)")

    try:
        token = _get_access_token()
    except DefaultCredentialsError as exc:
        raise MenuExtractionError("Could not obtain Google Cloud credentials for Vertex AI") from exc

    url = (
        f"https://{settings.vertex_ai_location}-aiplatform.googleapis.com/v1/projects/"
        f"{settings.gcp_project_id}/locations/{settings.vertex_ai_location}/publishers/google/"
        f"models/{GEMINI_MODEL}:generateContent"
    )
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": EXTRACTION_PROMPT},
                    {"inline_data": {"mime_type": mime_type, "data": base64.b64encode(image_bytes).decode()}},
                ],
            }
        ],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(url, headers={"Authorization": f"Bearer {token}"}, json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Vertex AI menu extraction request failed: %s", exc)
            raise MenuExtractionError("The menu extraction service request failed") from exc

    body = response.json()
    try:
        text = body["candidates"][0]["content"]["parts"][0]["text"]
        raw_items = json.loads(text)
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        logger.warning("Could not parse Vertex AI menu extraction response: %s", exc)
        raise MenuExtractionError("Couldn't read the model's response") from exc

    items: list[ExtractedMenuItem] = []
    for raw in raw_items if isinstance(raw_items, list) else []:
        try:
            items.append(ExtractedMenuItem(**raw))
        except (ValidationError, TypeError):
            continue  # skip a malformed entry rather than failing the whole extraction
    return items
