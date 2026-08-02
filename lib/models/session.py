"""
Authenticated session.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Session:

    user_id: int

    username: str

    token: str

    created_at: datetime

    expires_at: datetime

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(
        self,
    ) -> dict:

        return {
            "user_id": self.user_id,
            "username": self.username,
            "token": self.token,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
        }

    @classmethod
    def from_dict(
        cls,
        data: dict,
    ) -> "Session":

        return cls(
            user_id=data["user_id"],
            username=data["username"],
            token=data["token"],
            created_at=datetime.fromisoformat(
                data["created_at"],
            ),
            expires_at=datetime.fromisoformat(
                data["expires_at"],
            ),
        )
