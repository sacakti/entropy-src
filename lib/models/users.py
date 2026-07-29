from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class User:

    id: Optional[int] = None

    username: str = ""

    password_hash: str = ""

    full_name: Optional[str] = None

    email: Optional[str] = None

    group_id: Optional[int] = None

    system: bool = False

    is_active: bool = True

    created_at: Optional[datetime] = None

    updated_at: Optional[datetime] = None

    @property
    def is_new(self) -> bool:
        return self.id is None
