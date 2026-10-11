"""Comandi Telegram del bot."""
import html
import re
from typing import List, Optional, Tuple

from . import config
from .extract import clean, parse_mq, parse_price
from .models import Listing
from .store import Store

# Caratteristiche riconosciute nei filtri: si cercano nel titolo, nel testo e nel link dell'annuncio.
FEATURES = {
    "giardino": ["giardino", "resede", "corte esclusiva"],
    "terrazza": ["terrazza", "terrazzo"],
    "balcone": ["balcone", "balconi"],
    "garage": ["garage", "box auto", "autorimessa"],
    "posto auto": ["posto auto", "posti auto"],
    "piscina": ["piscina"],
    "cantina": ["cantina"],
    "ascensore": ["ascensore"],
    "indipendente": ["indipendente", "terratetto", "terra tetto", "villa", "villetta", "colonica", "casale", "rustico"],
    "villa": ["villa", "villetta"],
    "rustico": ["rustico", "colonica", "casale"],
    "appartamento": ["appartamento", "bilocale", "trilocale", "quadrilocale"],
    "vista": ["vista", "panoramic"],
}


HELP = (
    "<b>Bot cerca casa</b>, vendite in Valdarno e primo Chianti.\n\n"
    "/cerca [comune] [max 250000] [mq 80]: annunci salvati che rispettano i filtri\n"
    "/ultimi: gli ultimi 10 annunci trovati\n"
    "/filtro max 300000 mq 70 giardino: ricevi avvisi solo per questi annunci (/filtro off per toglierlo)\n"
    "Parole che capisco nei filtri: " + ", ".join(FEATURES) + "\n"
    "/comuni: i comuni seguiti\n"
    "/fonti: quante fonti sto controllando\n\n"
    "Puoi anche inoltrarmi un annuncio visto altrove (Facebook, WhatsApp...): lo salvo insieme agli altri."
)

_URL = re.compile(r"https?://\S+")


def fmt_price(p: Optional[int]) -> str:
    return f"€ {p:,}".replace(",", ".") if p else "prezzo n.d."


def fmt_listing(d: dict) -> str:
    parts = [fmt_price(d.get("price"))]
    if d.get("mq"):
        parts.append(f"{d['mq']} mq")
    parts.append(d.get("comune") or "comune n.d.")
    lines = [f"<b>{html.escape(d.get('title') or 'Annuncio')}</b>", " · ".join(parts),
             f"{html.escape(d['source'])}: {html.escape(d['url'])}"]
    for other in d.get("also_on", [])[:3]:
        lines.append(f"anche su {html.escape(other)}")
    return "\n".join(lines)


def parse_features(text: str) -> List[str]:
    t = f" {config.normalize(text)} "
    return [f for f in FEATURES if f" {config.normalize(f)}" in t]


def has_features(d: dict, features: List[str]) -> bool:
    blob = config.normalize(" ".join([d.get("title") or "", d.get("text") or "", d.get("url") or ""]))
    return all(any(config.normalize(w) in blob for w in FEATURES[f]) for f in features)


def parse_filters(text: str) -> Tuple[Optional[str], Optional[int], Optional[int]]:
    t = config.normalize(text)
    comune = None
    for c, frazioni in config.COMUNI.items():
        if config.normalize(c) in t or any(f" {config.normalize(f)} " in f" {t} " for f in frazioni):
            comune = c
            break
    max_price = None
    m = re.search(r"(?:max|fino a|sotto|<)\s*([0-9.]+)\s*(k|mila)?", t)
    if m:
        max_price = int(m.group(1).replace(".", "")) * (1000 if m.group(2) else 1)
    min_mq = None
    m = re.search(r"(?:mq|metri)\s*([0-9]+)|([0-9]+)\s*mq", t)
    if m:
        min_mq = int(m.group(1) or m.group(2))
    return comune, max_price, min_mq


def matches_filter(d: dict, flt: dict) -> bool:
    if not flt:
        return True
    if flt.get("max_price") and d.get("price") and d["price"] > flt["max_price"]:
        return False
    if flt.get("min_mq") and d.get("mq") and d["mq"] < flt["min_mq"]:
        return False
    if flt.get("comuni") and d.get("comune") and d["comune"] not in flt["comuni"]:
        return False
    if flt.get("features") and not has_features(d, flt["features"]):
        return False
    return True


def authorized(store: Store, chat_id: str) -> bool:
    allowed = config.TELEGRAM_ALLOWED_CHATS or store.data["chats"]
    return chat_id in allowed


def handle(store: Store, message: dict, n_sources: int) -> Optional[str]:
    chat_id = str(message["chat"]["id"])
    text = (message.get("text") or message.get("caption") or "").strip()
    if text.startswith("/start"):
        if not config.TELEGRAM_ALLOWED_CHATS and not store.data["chats"]:
            store.data["chats"].append(chat_id)
            return "Ciao! Da ora ti avviso dei nuovi annunci in vendita nella tua zona.\n\n" + HELP
        if authorized(store, chat_id):
            return HELP
        return "Questo bot è privato."
    if not authorized(store, chat_id):
        return None

    cmd, _, args = text.partition(" ")
    cmd = cmd.split("@")[0].lower()
    if cmd in ("/aiuto", "/help"):
        return HELP
    if cmd == "/comuni":
        return "Comuni seguiti:\n" + "\n".join(f"• {c}" for c in config.COMUNI)
    if cmd == "/fonti":
        return (f"Controllo {n_sources} siti di agenzie, più le email di avviso di portali, Subito e gruppi Facebook.\n"
                f"Annunci salvati finora: {len(store.listings)}.")
    if cmd in ("/cerca", "/ultimi"):
        comune, max_price, min_mq = parse_filters(args) if cmd == "/cerca" else (None, None, None)
        features = parse_features(args) if cmd == "/cerca" else []
        res = [d for d in store.search(comune, max_price, min_mq, limit=500) if has_features(d, features)][:10]
        if not res:
            return "Nessun annuncio salvato con questi filtri."
        head = f"{len(res)} annunci" + (f" a {comune}" if comune else "") + \
            (f", max {fmt_price(max_price)}" if max_price else "") + (f", almeno {min_mq} mq" if min_mq else "") + \
            (f", con {', '.join(features)}" if features else "")
        return head + ":\n\n" + "\n\n".join(fmt_listing(d) for d in res)
    if cmd == "/filtro":
        if args.strip().lower() in ("off", "no", "via", ""):
            store.data["filters"].pop(chat_id, None)
            return "Filtro tolto: ti avviso di tutti i nuovi annunci."
        comune, max_price, min_mq = parse_filters(args)
        flt = {"max_price": max_price, "min_mq": min_mq, "comuni": [comune] if comune else [],
               "features": parse_features(args)}
        store.data["filters"][chat_id] = flt
        return "Filtro salvato. " + describe_filter(flt)

    urls = _URL.findall(text)
    if urls:
        body = _URL.sub(" ", text)
        comune, _ = config.detect_comune(body, urls[0])
        l = Listing(url=urls[0], source="inoltrato", title=clean(body, 120) or urls[0],
                    price=parse_price(body), mq=parse_mq(body), comune=comune, text=clean(body, 400))
        status = store.add(l)
        return {"new": "Salvato. ", "dup": "Questo immobile c'era già da un'altra fonte, ho aggiunto il link. ",
                "known": "Questo annuncio lo avevo già. "}[status] + "Usa /cerca per ritrovarlo."
    return "Non ho capito. " + HELP


def describe_filter(flt: dict) -> str:
    bits = []
    if flt.get("comuni"):
        bits.append("solo " + ", ".join(flt["comuni"]))
    if flt.get("max_price"):
        bits.append("fino a " + fmt_price(flt["max_price"]))
    if flt.get("min_mq"):
        bits.append(f"almeno {flt['min_mq']} mq")
    if flt.get("features"):
        bits.append("con " + ", ".join(flt["features"]))
    return ("Ti avviso per annunci " + ", ".join(bits) + ".") if bits else "Ti avviso di tutti gli annunci."
