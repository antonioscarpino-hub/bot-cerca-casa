import hashlib
import re
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Listing:
    url: str
    source: str
    title: str = ""
    price: Optional[int] = None
    mq: Optional[int] = None
    comune: Optional[str] = None
    text: str = ""
    first_seen: str = ""
    also_on: list = field(default_factory=list)

    @property
    def id(self) -> str:
        return hashlib.sha1(canonical_url(self.url).encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["id"] = self.id
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Listing":
        d = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**d)


_TRACKING = re.compile(r"(utm_[a-z]+|fbclid|gclid|ref|src|from)=[^&]*&?", re.I)


def canonical_url(url: str) -> str:
    url = url.strip().split("#")[0]
    url = _TRACKING.sub("", url).rstrip("?&")
    url = re.sub(r"^http://", "https://", url)
    url = url.replace("://m.", "://www.")
    return url.rstrip("/")
