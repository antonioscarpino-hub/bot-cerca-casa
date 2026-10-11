"""Estrazione generica di prezzo, superficie e titolo dal testo di un annuncio."""
import re
from typing import Optional

_PRICE = re.compile(r"(?:€|euro|eur)\s*([0-9]{1,3}(?:[.'’][0-9]{3})+|[0-9]{4,7})(?:,[0-9]{2})?"
                    r"|([0-9]{1,3}(?:[.'’][0-9]{3})+|[0-9]{4,7})(?:,[0-9]{2})?\s*(?:€|euro)", re.I)
_MQ = re.compile(r"([0-9]{2,5})(?:[.,][0-9]+)?\s*(?:mq|m²|m2|metri quadri|sqm|m\^2)\b", re.I)


def parse_price(text: str) -> Optional[int]:
    best = None
    for m in _PRICE.finditer(text or ""):
        raw = m.group(1) or m.group(2)
        value = int(re.sub(r"[.'’]", "", raw))
        # Scarta numeri che non sono prezzi di vendita (spese, rate, affitti).
        if 10_000 <= value <= 20_000_000:
            best = value if best is None else best
    return best


def parse_mq(text: str) -> Optional[int]:
    for m in _MQ.finditer(text or ""):
        value = int(m.group(1))
        if 15 <= value <= 20_000:
            return value
    return None


def clean(text: str, limit: int = 0) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text[:limit].rstrip() + "…" if limit and len(text) > limit else text


def looks_like_rent(text: str) -> bool:
    t = (text or "").lower()
    return bool(re.search(r"\baffitt|\blocazione|\bin affitto|/mese|al mese|\bmensil", t)) and "vendita" not in t


def card_for(anchor, is_listing_link, max_up: int = 6, max_chars: int = 1500):
    """Risale dal link al riquadro dell'annuncio: si ferma prima di inglobare altri annunci."""
    own = anchor.get("href")
    node = anchor
    for _ in range(max_up):
        parent = node.parent
        if parent is None or parent.name in ("body", "html", "[document]"):
            break
        others = [a for a in parent.find_all("a", href=True) if a.get("href") != own and is_listing_link(a["href"])]
        if others or len(parent.get_text(" ", strip=True)) > max_chars:
            break
        node = parent
    return node
