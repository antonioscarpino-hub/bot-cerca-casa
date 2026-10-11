"""Lettore generico per i siti delle agenzie.

Ogni fonte è descritta in sources.json da: pagine elenco da leggere e una regex
che riconosce i link agli annunci di dettaglio. Per ogni link trovato si prende
il testo del "riquadro" che lo contiene (il primo antenato con un prezzo).
"""
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Iterable, List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .. import config
from ..extract import card_for, clean, looks_like_rent, parse_mq, parse_price
from ..models import Listing, canonical_url

log = logging.getLogger(__name__)


@dataclass
class WebSource:
    name: str
    list_urls: List[str]
    detail_regex: str
    comune: str = ""
    enabled: bool = True
    notes: str = ""
    exclude_regex: str = ""
    extra_headers: dict = field(default_factory=dict)

    def fetch(self, session: requests.Session) -> List[Listing]:
        found = {}
        for url in self.list_urls:
            try:
                resp = session.get(url, timeout=config.REQUEST_TIMEOUT, headers=self.extra_headers)
                resp.raise_for_status()
            except requests.RequestException as e:
                log.warning("%s: errore su %s: %s", self.name, url, e)
                continue
            for listing in parse_list_page(resp.text, resp.url, self):
                found.setdefault(listing.id, listing)
            time.sleep(1.5)  # gentile con i siti delle agenzie
        return list(found.values())


def parse_list_page(html: str, base_url: str, source: WebSource) -> Iterable[Listing]:
    soup = BeautifulSoup(html, "html.parser")
    rx = re.compile(source.detail_regex, re.I)
    ex = re.compile(source.exclude_regex, re.I) if source.exclude_regex else None
    seen = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"].strip())
        if not rx.search(href) or (ex and ex.search(href)):
            continue
        key = canonical_url(href)
        if key in seen:
            continue
        seen.add(key)
        card = card_for(a, lambda h: bool(rx.search(urljoin(base_url, h))))
        text = clean(card.get_text(" ", strip=True))
        if looks_like_rent(text + " " + href):
            continue
        title = clean(a.get("title") or a.get_text(" ", strip=True)) or _title_from(card)
        if len(title) < 4:
            title = _title_from(card) or href.rsplit("/", 1)[-1]
        comune, in_area = config.detect_comune(title, text, href)
        if not in_area:
            continue
        yield Listing(
            url=href,
            source=source.name,
            title=clean(title, 120),
            price=parse_price(text),
            mq=parse_mq(text),
            comune=comune or (source.comune or None),
            text=clean(text, 400),
        )


def _title_from(card) -> str:
    for tag in ("h1", "h2", "h3", "h4", "strong"):
        el = card.find(tag)
        if el and el.get_text(strip=True):
            return el.get_text(" ", strip=True)
    return ""


def load_sources(path: str = config.SOURCES_PATH) -> List[WebSource]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [WebSource(**s) for s in data if s.get("enabled", True)]


def new_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": config.USER_AGENT, "Accept-Language": "it-IT,it;q=0.9"})
    return s
