"""Web Push to the devices that turned notifications on.

The VAPID key pair is created on first use and kept in the store, so every
worker and restart signs with the same key and existing subscriptions keep
working. On iOS a subscription only exists for the app added to the Home
Screen (iOS 16.4+); the browser tab never gets one.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any
from urllib.parse import urlparse

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid02
from pywebpush import WebPushException, webpush

from .store import Store

log = logging.getLogger("mailgrant.web.push")


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


class Pusher:
    def __init__(self, store: Store, contact: str) -> None:
        self.store = store
        # RFC 8292 wants a mailto: or https: contact; push services drop pushes
        # from senders without one.
        self.contact = contact if contact.startswith(("mailto:", "https:")) else f"mailto:{contact}"
        self._vapid: Vapid02 | None = None

    def _keys(self) -> Vapid02:
        if self._vapid is not None:
            return self._vapid
        pem = self.store.get_pref("vapid_private_pem")
        if pem:
            vapid = Vapid02.from_pem(pem.encode("ascii"))
        else:
            vapid = Vapid02()
            vapid.generate_keys()
            pem = vapid.private_pem().decode("ascii")
            self.store.set_pref("vapid_private_pem", pem)
        self._vapid = vapid
        return vapid

    def public_key(self) -> str:
        """The applicationServerKey browsers subscribe with (uncompressed P-256, base64url)."""
        raw = self._keys().public_key.public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        return _b64url(raw)

    def send_all(self, payload: dict[str, Any]) -> int:
        """Deliver to every subscribed device; drops subscriptions the service says are gone."""
        sent = 0
        data = json.dumps(payload, ensure_ascii=False)
        for sub in self.store.push_subscriptions():
            info = {
                "endpoint": sub["endpoint"],
                "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
            }
            audience = "{0.scheme}://{0.netloc}".format(urlparse(sub["endpoint"]))
            try:
                webpush(
                    subscription_info=info,
                    data=data,
                    vapid_private_key=self._keys(),
                    vapid_claims={"sub": self.contact, "aud": audience},
                    ttl=24 * 3600,
                    timeout=10,
                )
                sent += 1
            except WebPushException as e:
                status = getattr(e.response, "status_code", None)
                if status in (404, 410):
                    self.store.remove_push(sub["endpoint"])
                else:
                    log.warning("push failed (%s): %s", status, str(e)[:200])
            except Exception as e:  # noqa: BLE001 - one bad device must not stop the rest
                log.warning("push failed: %s", str(e)[:200])
        return sent
