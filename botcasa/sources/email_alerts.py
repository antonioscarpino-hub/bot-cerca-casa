"""Legge le email di avviso (portali, Subito, gruppi Facebook) dalla casella dedicata al bot."""
import email
import imaplib
import logging
import re
from email.header import decode_header, make_header
from typing import List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlparse

import requests
from bs4 import BeautifulSoup

from .. import config
from ..extract import card_for, clean, looks_like_rent, parse_mq, parse_price
from ..models import Listing

log = logging.getLogger(__name__)

# (nome fonte, regex del link all'annuncio)
PORTALS: List[Tuple[str, re.Pattern]] = [
    ("immobiliare.it", re.compile(r"https?://(?:www\.)?immobiliare\.it/annunci/\d+", re.I)),
    ("idealista", re.compile(r"https?://(?:www\.)?idealista\.it/immobile/\d+", re.I)),
    ("casa.it", re.compile(r"https?://(?:www\.)?casa\.it/immobili/\d+", re.I)),
    ("wikicasa", re.compile(r"https?://(?:www\.)?wikicasa\.it/[^\s\"'<>]*?-\d{5,}/?", re.I)),
    ("subito.it", re.compile(r"https?://(?:www\.)?subito\.it/[a-z-]+/[^\s\"'<>]+?-\d{6,}\.htm", re.I)),
    ("facebook", re.compile(r"https?://(?:www\.|m\.)?facebook\.com/(?:groups/[^/\s\"'<>]+/(?:posts|permalink)/\d+"
                            r"|marketplace/item/\d+)", re.I)),
]

# Domini che nelle email usano link di tracciamento da risolvere.
TRACKING_HOSTS = ("click.", "links.", "email.", "e.", "track", "l.facebook.com", "lm.facebook.com", "sendgrid", "mailchi")

SALE_HINTS = re.compile(r"vend|in vendita|prezzo|€|euro|trattabil", re.I)
NOT_OFFER = re.compile(r"\bcerco\b|\bcerchiamo\b|\bcercasi\b|\baffitt|\bstanza\b|\bposto letto\b", re.I)


def _decode(value: Optional[str]) -> str:
    try:
        return str(make_header(decode_header(value or "")))
    except Exception:
        return value or ""


def match_portal(url: str) -> Optional[Tuple[str, str]]:
    for name, rx in PORTALS:
        m = rx.search(url)
        if m:
            return name, m.group(0)
    return None


def unwrap(url: str) -> str:
    """Estrae l'URL vero dai parametri di un link di tracciamento, se c'è."""
    for values in parse_qs(urlparse(url).query).values():
        for v in values:
            v = unquote(v)
            if v.startswith("http") and match_portal(v):
                return v
    return url


def resolve(url: str, session: Optional[requests.Session]) -> str:
    url = unwrap(url)
    if match_portal(url) or session is None:
        return url
    host = urlparse(url).netloc.lower()
    if not any(t in host for t in TRACKING_HOSTS):
        return url
    try:
        r = session.head(url, allow_redirects=True, timeout=config.REQUEST_TIMEOUT)
        return r.url
    except requests.RequestException:
        return url


def listings_from_html(html: str, sender: str, session: Optional[requests.Session] = None) -> List[Listing]:
    soup = BeautifulSoup(html, "html.parser")
    out = {}
    for a in soup.find_all("a", href=True):
        url = resolve(a["href"], session)
        hit = match_portal(url)
        if not hit:
            continue
        source, clean_url = hit
        # Il riquadro dell'annuncio: risali finché il testo resta di dimensione ragionevole.
        node = card_for(a, lambda h: bool(match_portal(unwrap(h))), max_chars=800)
        text = clean(node.get_text(" ", strip=True))
        listing = _make(source, clean_url, a.get_text(" ", strip=True), text)
        if listing and listing.id not in out:
            out[listing.id] = listing
    return list(out.values())


def listings_from_text(body: str) -> List[Listing]:
    out = {}
    for name, rx in PORTALS:
        for m in rx.finditer(body):
            start = max(0, m.start() - 400)
            ctx = clean(body[start:m.start()])
            listing = _make(name, m.group(0), "", ctx)
            if listing:
                out.setdefault(listing.id, listing)
    return list(out.values())


def _make(source: str, url: str, title: str, text: str) -> Optional[Listing]:
    if source == "facebook":
        # Nei gruppi passa di tutto: teniamo solo i post che sembrano offerte di vendita.
        if NOT_OFFER.search(text) or not SALE_HINTS.search(text):
            return None
    elif looks_like_rent(text):
        return None
    comune, in_area = config.detect_comune(title, text, url)
    if not in_area:
        return None
    return Listing(url=url, source=source, title=clean(title or text, 120), price=parse_price(text),
                   mq=parse_mq(text), comune=comune, text=clean(text, 400))


def fetch_alerts(session: Optional[requests.Session] = None) -> List[Listing]:
    if not (config.IMAP_USER and config.IMAP_PASSWORD):
        log.info("Casella email non configurata: salto gli avvisi email")
        return []
    results = {}
    with imaplib.IMAP4_SSL(config.IMAP_HOST) as imap:
        imap.login(config.IMAP_USER, config.IMAP_PASSWORD)
        imap.select("INBOX")
        _, data = imap.search(None, "UNSEEN")
        for num in data[0].split():
            _, msg_data = imap.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])
            sender = _decode(msg.get("From"))
            found = []
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype not in ("text/html", "text/plain"):
                    continue
                payload = part.get_payload(decode=True) or b""
                body = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                found += listings_from_html(body, sender, session) if ctype == "text/html" else listings_from_text(body)
            for l in found:
                results.setdefault(l.id, l)
            imap.store(num, "+FLAGS", "\\Seen")
            log.info("Email da %s: %d annunci", sender, len(found))
    return list(results.values())
