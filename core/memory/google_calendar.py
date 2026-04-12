"""Google Calendar client: fetches credentials from env and exposes CRUD ops.

Refresh token is the long-lived credential. Access tokens are minted on demand
by the google-auth library.
"""

from __future__ import annotations

import os
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _credentials() -> Credentials:
    client_id = os.environ["GOOGLE_OAUTH_CLIENT_ID"]
    client_secret = os.environ["GOOGLE_OAUTH_CLIENT_SECRET"]
    refresh_token = os.environ["GOOGLE_OAUTH_REFRESH_TOKEN"]
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
    if not creds.valid:
        creds.refresh(Request())
    return creds


class GoogleCalendarClient:
    def __init__(self, calendar_id: str = "primary"):
        self.calendar_id = calendar_id
        self._service = None

    @property
    def service(self):
        if self._service is None:
            self._service = build("calendar", "v3", credentials=_credentials(), cache_discovery=False)
        return self._service

    def list_events(self, start_iso: str, end_iso: str) -> list[dict]:
        resp = self.service.events().list(
            calendarId=self.calendar_id,
            timeMin=start_iso,
            timeMax=end_iso,
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        return [
            {
                "id": e["id"],
                "title": e.get("summary", ""),
                "start": e["start"].get("dateTime") or e["start"].get("date"),
                "end": e["end"].get("dateTime") or e["end"].get("date"),
                "description": e.get("description", ""),
            }
            for e in resp.get("items", [])
        ]

    def create_event(
        self, title: str, start_iso: str, end_iso: str, description: str | None = None
    ) -> dict:
        body: dict[str, Any] = {
            "summary": title,
            "start": {"dateTime": start_iso},
            "end": {"dateTime": end_iso},
        }
        if description:
            body["description"] = description
        created = self.service.events().insert(calendarId=self.calendar_id, body=body).execute()
        return {"id": created["id"]}

    def update_event(
        self,
        event_id: str,
        *,
        title: str | None = None,
        start_iso: str | None = None,
        end_iso: str | None = None,
        description: str | None = None,
    ) -> dict:
        event = self.service.events().get(calendarId=self.calendar_id, eventId=event_id).execute()
        if title is not None:
            event["summary"] = title
        if start_iso is not None:
            event["start"] = {"dateTime": start_iso}
        if end_iso is not None:
            event["end"] = {"dateTime": end_iso}
        if description is not None:
            event["description"] = description
        updated = self.service.events().update(
            calendarId=self.calendar_id, eventId=event_id, body=event
        ).execute()
        return {"id": updated["id"]}

    def delete_event(self, event_id: str) -> dict:
        self.service.events().delete(calendarId=self.calendar_id, eventId=event_id).execute()
        return {"ok": True}
