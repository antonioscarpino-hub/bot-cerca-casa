import os

import pytest

from botcasa import config
from botcasa.commands import handle, parse_filters
from botcasa.extract import parse_mq, parse_price
from botcasa.models import Listing
from botcasa.sources.email_alerts import listings_from_html, listings_from_text
from botcasa.sources.web import WebSource, parse_list_page
from botcasa.store import Store

AGESTA_HTML = """
<html><body><div id="elenco">
 <div class="annuncio"><a href="immobile_dettaglio.asp?cod_annuncio=2604928&language=ita">
   <h3>Appartamento ottime condizioni a San Giovanni Valdarno</h3></a>
   <span>€ 245.000</span><span>180 Mq</span></div>
 <div class="annuncio"><a href="immobile_dettaglio.asp?cod_annuncio=2596014&language=ita">
   <h3>Villetta a Arezzo</h3></a><span>€ 310.000</span><span>140 Mq</span></div>
 <div class="annuncio"><a href="immobile_dettaglio.asp?cod_annuncio=2590457&language=ita">
   <h3>Bilocale in affitto a Montevarchi</h3></a><span>€ 600 /mese</span></div>
 <a href="javascript:change_page(2);">Avanti</a>
</div></body></html>
"""


def test_parse_price_and_mq():
    assert parse_price("Prezzo: € 245.000 trattabili") == 245000
    assert parse_price("1.980.000 €") == 1980000
    assert parse_price("spese condominiali € 80") is None
    assert parse_mq("superficie 180 Mq, giardino") == 180
    assert parse_mq("615 m2") == 615


def test_detect_comune():
    assert config.detect_comune("Villa a Castelnuovo dei Sabbioni") == ("Cavriglia", True)
    assert config.detect_comune("casa-singola-castelfranco-piandisco") == ("Castelfranco Piandiscò", True)
    assert config.detect_comune("Appartamento centro Arezzo") == ("Arezzo", False)
    assert config.detect_comune("Rustico con vista") == (None, True)


def test_parse_list_page_agestaweb():
    src = WebSource(name="Immobiliare Più", list_urls=[], detail_regex=r"immobile_dettaglio\.asp\?cod_annuncio=\d+")
    res = list(parse_list_page(AGESTA_HTML, "https://www.immobiliarepiu.it/web/immobili.asp", src))
    assert len(res) == 1  # Arezzo è fuori area, l'affitto è scartato
    l = res[0]
    assert l.url == "https://www.immobiliarepiu.it/web/immobile_dettaglio.asp?cod_annuncio=2604928&language=ita"
    assert (l.price, l.mq, l.comune) == (245000, 180, "San Giovanni Valdarno")


def test_email_portal_and_tracking_link():
    html = """<table><tr><td>
      <a href="https://click.immobiliare.it/r?u=https%3A%2F%2Fwww.immobiliare.it%2Fannunci%2F123456789%2F%3Futm_source%3Dmail">
      Trilocale via Roma, Figline e Incisa Valdarno</a><p>€ 189.000 · 85 m²</p></td></tr></table>"""
    res = listings_from_html(html, "immobiliare.it")
    assert len(res) == 1
    assert res[0].url == "https://www.immobiliare.it/annunci/123456789"
    assert (res[0].price, res[0].mq, res[0].comune) == (189000, 85, "Figline e Incisa Valdarno")


def test_email_facebook_group_filters_requests():
    html = """
    <div><p>Vendo casa colonica a Loro Ciuffenna, 200 mq con giardino, 230.000 euro</p>
      <a href="https://www.facebook.com/groups/casevaldarno/posts/111111111">Vedi post</a></div>
    <div><p>Cerco appartamento in affitto a Montevarchi</p>
      <a href="https://www.facebook.com/groups/casevaldarno/posts/222222222">Vedi post</a></div>"""
    res = listings_from_html(html, "Facebook")
    assert [l.url for l in res] == ["https://www.facebook.com/groups/casevaldarno/posts/111111111"]
    assert res[0].comune == "Loro Ciuffenna" and res[0].price == 230000


def test_email_plain_text_subito():
    body = "Nuovo annuncio: Casa indipendente a Bucine 120 mq € 150.000\nhttps://www.subito.it/appartamenti/casa-bucine-567891234.htm"
    res = listings_from_text(body)
    assert len(res) == 1 and res[0].source == "subito.it" and res[0].comune == "Bucine"


def test_store_dedup_and_search(tmp_path):
    s = Store(str(tmp_path / "state.json"))
    a = Listing(url="https://a.it/1", source="A", title="Casa", price=200000, mq=100, comune="Cavriglia")
    b = Listing(url="https://b.it/9", source="B", title="Casa", price=200000, mq=101, comune="Cavriglia")
    assert s.add(a) == "new"
    assert s.add(a) == "known"
    assert s.add(b) == "dup"
    assert s.listings[a.id]["also_on"] == ["B: https://b.it/9"]
    assert len(s.search("Cavriglia", 250000, 90)) == 1
    assert s.search("Cavriglia", 150000) == []
    s.save()
    assert Store(str(tmp_path / "state.json")).listings.keys() == s.listings.keys()


def test_commands(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_ALLOWED_CHATS", [])
    s = Store(str(tmp_path / "state.json"))
    msg = lambda chat, text: {"chat": {"id": chat}, "text": text}
    assert "Ciao" in handle(s, msg(1, "/start"), 10)
    assert handle(s, msg(2, "/cerca"), 10) is None  # chat non autorizzata
    assert "Salvato" in handle(s, msg(1, "Guarda questa villa a Gaiole 350.000 € https://facebook.com/marketplace/item/42"), 10)
    out = handle(s, msg(1, "/cerca gaiole max 400k"), 10)
    assert "€ 350.000" in out and "Gaiole in Chianti" in out
    assert "fino a € 300.000" in handle(s, msg(1, "/filtro max 300000 mq 70"), 10)
    assert parse_filters("figline sotto 250.000 80 mq") == ("Figline e Incisa Valdarno", 250000, 80)


def test_sources_json_is_valid():
    from botcasa.sources.web import load_sources
    import re
    for src in load_sources():
        re.compile(src.detail_regex)
        assert src.list_urls and all(u.startswith("http") for u in src.list_urls)


def test_robots_respected():
    from botcasa.sources import web

    class Resp:
        status_code = 200
        text = "User-agent: *\nDisallow: /privato/\n"

    class Sess:
        def get(self, url, timeout=None):
            return Resp()

    web._robots_cache.clear()
    assert web.allowed_by_robots(Sess(), "https://agenzia.it/annunci/")
    assert not web.allowed_by_robots(Sess(), "https://agenzia.it/privato/x")
