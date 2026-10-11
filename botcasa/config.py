import os
import re
import unicodedata

# Comuni dell'area di ricerca. Le frazioni servono a riconoscere il comune
# quando l'annuncio cita solo la località.
COMUNI = {
    "Montevarchi": ["levanella", "moncioni", "mercatale valdarno", "ricasoli", "rendola", "caposelvi"],
    "San Giovanni Valdarno": ["san giovanni v.no", "s. giovanni valdarno", "san giovanni valdarno"],
    "Terranuova Bracciolini": ["terranuova", "penna di terranuova", "cicogna", "malva", "persignano", "campogialli", "montemarciano"],
    "Cavriglia": ["castelnuovo dei sabbioni", "santa barbara", "meleto", "vacchereccia", "montegonzi", "san cipriano", "massa sabbioni"],
    "Bucine": ["ambra", "levane", "badia agnano", "san pancrazio", "pietraviva", "capannole", "montebenichi"],
    "Castelfranco Piandiscò": ["castelfranco di sopra", "pian di scò", "pian di sco", "piandiscò", "piandisco", "faella", "vaggio", "certignano", "castelfranco piandisco"],
    "Loro Ciuffenna": ["san giustino valdarno", "querceto", "gangheretto", "modine"],
    "Laterina Pergine Valdarno": ["laterina", "pergine valdarno", "montalto", "casanuova"],
    "Figline e Incisa Valdarno": ["figline", "incisa", "matassino", "burchio", "gaville", "brollo", "restone", "palazzolo", "cesto", "lagaccioni"],
    "Reggello": ["cascia", "leccio", "vallombrosa", "pietrapiana", "sant'ellero", "donnini", "saltino", "matassino reggello", "ciliegi"],
    "Rignano sull'Arno": ["rignano", "san donato in collina", "troghi", "rosano"],
    "Greve in Chianti": ["greve", "strada in chianti", "panzano", "lucolena", "lamole", "montefioralle", "dudda", "chiocchio"],
    "Gaiole in Chianti": ["gaiole", "monti in chianti", "lecchi", "castagnoli"],
    "Radda in Chianti": ["radda", "volpaia", "lucarelli"],
}

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
# Chat autorizzate, separate da virgola. Se vuota, la prima chat che scrive /start diventa proprietaria.
TELEGRAM_ALLOWED_CHATS = [c.strip() for c in os.environ.get("TELEGRAM_ALLOWED_CHATS", "").split(",") if c.strip()]

IMAP_HOST = os.environ.get("IMAP_HOST", "imap.gmail.com")
IMAP_USER = os.environ.get("IMAP_USER", "")
IMAP_PASSWORD = os.environ.get("IMAP_PASSWORD", "")

STATE_PATH = os.environ.get("STATE_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "state.json"))
SOURCES_PATH = os.path.join(os.path.dirname(__file__), "sources.json")

USER_AGENT = "Mozilla/5.0 (compatible; bot-cerca-casa/0.1; uso personale)"
REQUEST_TIMEOUT = 25


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9'.]+", " ", text.lower())
    text = re.sub(r"\.(?=\s|$)", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# Fuori area: comuni vicini che compaiono spesso negli elenchi delle agenzie.
FUORI_AREA = ["arezzo", "firenze", "siena", "pontassieve", "bagno a ripoli", "castelnuovo berardenga",
              "civitella in val di chiana", "monte san savino", "castiglion fibocchi", "pelago", "impruneta",
              "san casciano", "castellina in chianti", "rufina", "londa", "subbiano", "capolona"]


def detect_comune(*texts: str):
    """Restituisce (comune, in_area). comune è None se non riconosciuto."""
    blob = " " + " ".join(normalize(t) for t in texts if t) + " "
    for comune in COMUNI:
        if f" {normalize(comune)} " in blob:
            return comune, True
    for comune, frazioni in COMUNI.items():
        for f in frazioni:
            if f" {normalize(f)} " in blob:
                return comune, True
    for c in FUORI_AREA:
        if f" {normalize(c)} " in blob:
            return c.title(), False
    return None, True
