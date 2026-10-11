"""Stato del bot in un file JSON, salvato nel repository dal workflow dopo ogni giro."""
import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .models import Listing

MAX_LISTINGS = 5000


class Store:
    def __init__(self, path: str):
        self.path = path
        self.data = {"listings": {}, "seeded_sources": [], "telegram_offset": 0, "chats": [], "filters": {}}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.data.update(json.load(f))

    @property
    def listings(self) -> Dict[str, dict]:
        return self.data["listings"]

    def is_seeded(self, source: str) -> bool:
        return source in self.data["seeded_sources"]

    def mark_seeded(self, source: str):
        if source not in self.data["seeded_sources"]:
            self.data["seeded_sources"].append(source)

    def find_duplicate(self, l: Listing) -> Optional[dict]:
        """Stesso immobile pubblicato da un'altra fonte: stesso comune, prezzo e superficie."""
        if not (l.comune and l.price and l.mq):
            return None
        for d in self.listings.values():
            if d["source"] != l.source and d.get("comune") == l.comune and d.get("price") == l.price \
                    and d.get("mq") and abs(d["mq"] - l.mq) <= 3:
                return d
        return None

    def add(self, l: Listing) -> str:
        """Restituisce 'new', 'dup' o 'known'."""
        if l.id in self.listings:
            return "known"
        dup = self.find_duplicate(l)
        if dup:
            entry = f"{l.source}: {l.url}"
            if entry not in dup["also_on"]:
                dup["also_on"].append(entry)
            return "dup"
        l.first_seen = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.listings[l.id] = l.to_dict()
        return "new"

    def search(self, comune: Optional[str] = None, max_price: Optional[int] = None,
               min_mq: Optional[int] = None, limit: int = 10) -> List[dict]:
        items = sorted(self.listings.values(), key=lambda d: d.get("first_seen", ""), reverse=True)
        out = []
        for d in items:
            if comune and d.get("comune") != comune:
                continue
            if max_price and (not d.get("price") or d["price"] > max_price):
                continue
            if min_mq and (not d.get("mq") or d["mq"] < min_mq):
                continue
            out.append(d)
            if len(out) >= limit:
                break
        return out

    def save(self):
        if len(self.listings) > MAX_LISTINGS:
            keep = sorted(self.listings.items(), key=lambda kv: kv[1].get("first_seen", ""))[-MAX_LISTINGS:]
            self.data["listings"] = dict(keep)
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=1, sort_keys=True)
        os.replace(tmp, self.path)
