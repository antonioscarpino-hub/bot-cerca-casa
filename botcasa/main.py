"""Un giro del bot: risponde ai messaggi, controlla le fonti, invia gli avvisi, salva lo stato.

Pensato per girare ogni 15 minuti su GitHub Actions (python -m botcasa.main).
"""
import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

from . import config
from .commands import fmt_listing, handle, matches_filter
from .sources import email_alerts
from .sources.web import load_sources, new_session
from .store import Store
from .telegram import Telegram

log = logging.getLogger("botcasa")


def process_updates(tg: Telegram, store: Store, n_sources: int):
    for upd in tg.updates(store.data["telegram_offset"]):
        store.data["telegram_offset"] = upd["update_id"] + 1
        msg = upd.get("message")
        if not msg:
            continue
        reply = handle(store, msg, n_sources)
        if reply:
            tg.send(msg["chat"]["id"], reply)


def collect(store: Store, session, only: str = "") -> list:
    """Raccoglie gli annunci da tutte le fonti e restituisce quelli nuovi da notificare."""
    to_notify = []
    sources = load_sources()
    for src in sources:
        if only and only.lower() not in src.name.lower():
            continue
        listings = src.fetch(session)
        seeded = store.is_seeded(src.name)
        new = [l for l in listings if store.add(l) == "new"]
        log.info("%s: %d annunci letti, %d nuovi%s", src.name, len(listings), len(new),
                 "" if seeded else " (primo giro, nessun avviso)")
        if listings:
            store.mark_seeded(src.name)
        if seeded:
            to_notify += new
    if not only:
        try:
            for l in email_alerts.fetch_alerts(session):
                if store.add(l) == "new":
                    to_notify.append(l)
        except Exception as e:  # una casella email in errore non deve fermare il resto
            log.warning("Errore lettura email: %s", e)
    return to_notify


def notify(tg: Telegram, store: Store, listings: list):
    for chat_id in config.TELEGRAM_ALLOWED_CHATS or store.data["chats"]:
        flt = store.data["filters"].get(str(chat_id), {})
        wanted = [l for l in listings if matches_filter(l.to_dict(), flt)]
        for l in wanted[:30]:
            tg.send(chat_id, "🏠 Nuovo annuncio\n" + fmt_listing(store.listings.get(l.id, l.to_dict())))
        if len(wanted) > 30:
            tg.send(chat_id, f"…e altri {len(wanted) - 30} annunci nuovi. Usa /ultimi per vederli.")


def scrape_due(store: Store) -> bool:
    """Le fonti si controllano meno spesso dei messaggi, per stare nei minuti gratuiti di GitHub Actions."""
    every = int(os.environ.get("SCRAPE_EVERY_MIN", "180"))
    last = store.data.get("last_scrape")
    if not last:
        return True
    return datetime.now(timezone.utc) - datetime.fromisoformat(last) >= timedelta(minutes=every - 5)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="legge le fonti e stampa gli annunci senza Telegram né salvataggio")
    p.add_argument("--only", default="", help="controlla solo le fonti il cui nome contiene questo testo")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    session = new_session()
    if args.dry_run:
        for src in load_sources():
            if args.only and args.only.lower() not in src.name.lower():
                continue
            listings = src.fetch(session)
            print(f"== {src.name}: {len(listings)} annunci")
            for l in listings[:5]:
                print(f"   {l.price} | {l.mq} mq | {l.comune} | {l.title[:60]} | {l.url}")
        return 0
    store = Store(config.STATE_PATH)
    if not config.TELEGRAM_TOKEN:
        log.error("Manca TELEGRAM_TOKEN")
        return 1
    tg = Telegram(config.TELEGRAM_TOKEN)
    n_sources = len(load_sources())
    process_updates(tg, store, n_sources)
    store.save()  # salva subito l'offset, così un errore dopo non fa ripetere le risposte
    if args.only or scrape_due(store):
        notify(tg, store, collect(store, session, args.only))
        store.data["last_scrape"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    store.save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
