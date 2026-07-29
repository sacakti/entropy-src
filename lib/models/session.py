from dataclasses import dataclass
from datetime import datetime


@dataclass
class Session:

    username: str

    token: str

    created_at: datetime

    expires_at: datetime
