# bot-cerca-casa

Il bot Telegram raccoglie gli annunci di case in vendita nel Valdarno (aretino e fiorentino) e nel primo Chianti, anche quelli un po' nascosti. Ti avvisa quando esce un annuncio nuovo e ti permette di cercare tra quelli già trovati.

## Da dove prende gli annunci

- **Siti delle agenzie della zona:** l'elenco è in `botcasa/sources.json`. Ogni fonte indica le pagine con gli annunci in vendita e il formato dei link ai singoli annunci.
- **Email di avviso nella casella dedicata al bot:**
  - le ricerche salvate su immobiliare.it, idealista, casa.it, wikicasa e Subito;
  - le notifiche email dei gruppi Facebook di case in zona (il bot tiene solo i post che sembrano offerte di vendita).
- **Annunci inoltrati a mano:** se mandi al bot un messaggio con un link, lo salva insieme agli altri.

Il bot tiene solo gli annunci dei comuni seguiti (elenco in `botcasa/config.py`) e scarta gli affitti. Quando lo stesso immobile compare su più fonti, con stesso comune, prezzo e metratura, ti avvisa una volta sola e aggiunge i link delle altre fonti.

## Comandi Telegram

| Comando | Cosa fa |
|---|---|
| `/cerca cavriglia max 250000 mq 80` | cerca tra gli annunci salvati (comune, prezzo massimo e metri minimi sono tutti opzionali) |
| `/ultimi` | mostra gli ultimi 10 annunci trovati |
| `/filtro max 300000 mq 70` | manda gli avvisi solo per gli annunci che rispettano il filtro (`/filtro off` lo toglie) |
| `/comuni`, `/fonti`, `/aiuto` | informazioni sul bot |

## Come gira

Il bot gira su GitHub Actions (`.github/workflows/bot.yml`):

- **Messaggi Telegram:** ogni 20 minuti legge i messaggi che hai scritto e risponde.
- **Fonti:** ogni 3 ore controlla siti ed email. Puoi cambiare la frequenza con la variabile `SCRAPE_EVERY_MIN`.
- **Stato:** gli annunci salvati e la posizione nella chat stanno in `data/state.json`, che il workflow salva nel repository dopo ogni giro.
- **Primo giro:** la prima volta che il bot legge un sito, salva gli annunci senza mandare avvisi. Così non arrivano centinaia di messaggi.

## Configurazione (una volta sola)

In GitHub → Settings → Secrets and variables → Actions → **New repository secret**:

| Secret | Valore |
|---|---|
| `TELEGRAM_TOKEN` | il token dato da BotFather |
| `IMAP_USER` | l'indirizzo Gmail del bot |
| `IMAP_PASSWORD` | una **password per le app** di Gmail (Account Google → Sicurezza → Verifica in due passaggi → Password per le app) |
| `TELEGRAM_ALLOWED_CHATS` | facoltativo: id delle chat autorizzate. Se lo lasci vuoto, la prima chat che scrive `/start` diventa la proprietaria |

Per l'email servono anche due impostazioni su Gmail: **IMAP attivo** (Impostazioni → Inoltro e POP/IMAP) e la verifica in due passaggi, necessaria per creare la password per le app.

## Sviluppo

```bash
pip install -r requirements.txt pytest
pytest -q
python -m botcasa.main --dry-run --only abita   # legge una fonte e stampa gli annunci, senza Telegram
```
