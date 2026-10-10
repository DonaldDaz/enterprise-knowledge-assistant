# Enterprise Knowledge Assistant

Demo didattica di un assistente RAG per documenti aziendali **interamente sintetici**. Una sola pagina mostra upload, ricerca, citazioni, astensione, ruoli, stato dell'indicizzazione e statistiche. Il repository è pensato come esempio completo e leggibile, non come servizio pronto per dati reali.

## Avvio rapido

Richiede Docker con Compose v2. Da questa cartella:

```bash
cp .env.example .env
docker compose up --build -d --wait
```

Apri **http://localhost:5173**. Scegli un ruolo (`employee`, `hr`, `finance`, `admin`) e inserisci la relativa password di `.env`. I valori in `.env.example` sono solo per la demo locale. L'API è su **http://localhost:8000/docs**, la console MinIO su **http://localhost:9001** e i trace su **http://localhost:16686**. I servizi sono esposti solo su `127.0.0.1`.

Al primo avvio vengono importati tre file in `demo/`. L'amministratore può caricare file Markdown, TXT UTF-8 o PDF con testo estraibile, fino a 1 MB. Un PDF scansito senza OCR viene rifiutato.

Per fermare lo stack: `docker compose down`. Per cancellare anche i dati locali: `docker compose down -v`.

## Flusso dimostrativo

1. Scegli **Dipendente** e chiedi «Qual è il limite per un hotel per notte?». La risposta deve citare *Trasferte e rimborsi → Pernottamento*.
2. Scegli **Team HR** e chiedi del congedo parentale. La fonte è *Manuale persone → Congedo parentale*.
3. Ripeti la domanda come **Dipendente**: il manuale HR non è visibile e l'assistente si astiene.
4. Scegli **Admin**, carica un documento fittizio, assegna i ruoli e osserva stato, sezioni e statistiche sulla stessa pagina.
5. Apri Jaeger e cerca il servizio `enterprise-knowledge-api`: gli span mostrano ingestione, embedding, retrieval e generazione senza testo di domande o documenti.

Lo script `bash scripts/demo-flow.sh` esegue upload → domanda → statistiche via HTTP e legge le credenziali da `.env`.

## Test e valutazione

Con lo stack avviato:

```bash
docker compose exec -T api pytest -q tests
docker compose exec -T api ruff check app tests
python3 scripts/evaluate.py
```

I test di integrazione verificano upload, indicizzazione, separazione dei ruoli, citazione della sezione e astensione. `demo/questions.json` contiene domande con risposte attese e due casi senza risposta. La valutazione misura:

| Misura | Definizione |
|---|---|
| Correttezza delle citazioni | Risposta contenente il fatto atteso, titolo e sezione corretti, citazione uguale alla frase resa |
| Astensione corretta | Nessuna risposta attribuita né citazione per domande non supportate o fuori permesso |
| Latenza | Media e p95 dei tempi restituiti dall'API |
| Costo stimato | Somma del prezzo configurato per i token stimati; con provider locale il default è $0 |

Il workflow GitHub Actions costruisce lo stack, esegue lint, test e valutazione. I dati dei test sono sintetici.

## Perché queste scelte

- **MinIO** conserva gli originali; PostgreSQL conserva metadati e sezioni ricercabili. Un `document_id` collega i due sistemi.
- **pgvector** esegue la distanza coseno in SQL. Il filtro sul ruolo è nella query, prima di `ORDER BY`, così una fonte non autorizzata non entra nel contesto di risposta. L'amministratore può leggere tutti i documenti per ispezionarli.
- **Provider sostituibili**: `EmbeddingProvider` e `AnswerProvider` in `backend/app/rag.py` definiscono il confine per un servizio reale. La modalità locale usa feature hashing e una risposta estrattiva: nessuna API a pagamento, risultato riproducibile e citazione letterale. Non simula la comprensione semantica di un LLM.
- **Astensione**: la risposta viene generata solo se una frase recuperata supera la soglia di sovrapposizione lessicale. È un criterio spiegabile ma limitato; la valutazione deve crescere prima di sostituirlo con un modello generativo.
- **Osservabilità**: Jaeger riceve span OpenTelemetry con conteggi, ruolo e stato di astensione. Il database delle richieste non conserva prompt, risposte, nomi file o testo dei documenti.
- **Costi e limiti**: `.env` configura richieste al minuto, costo massimo per richiesta, budget giornaliero e prezzo per mille token. La stima usa `(caratteri domanda + 1200) / 4` token, una convenzione esplicita utile per la demo, non una fatturazione reale.

Il diagramma e la sequenza dettagliata sono in [docs/architecture.md](docs/architecture.md).

## Limiti intenzionali

Gli account sono fissi e le password demo sono note; cambiare `.env` è necessario prima di qualunque esposizione esterna. Autenticazione aziendale, gestione utenti e rotazione dei segreti sono fuori ambito. L'indicizzazione è sincrona: rende lo stato `ready` immediatamente verificabile ma un corpus grande richiederebbe una coda e retry. Il chunking dei PDF non conserva la pagina e non fa OCR. Il provider locale usa parole condivise, quindi parafrasi complesse e sinonimi possono portare ad astensioni. Il budget giornaliero è misurato in SQL senza prenotazioni atomiche e non è adatto a richieste concorrenti ad alto volume. Il parsing dei file è una demo: per file non affidabili servirebbe isolamento del parser, antivirus e controlli aggiuntivi.

L'immagine MinIO è una build community di [coollabsio/minio](https://github.com/coollabsio/minio) fissata a una release, perché le immagini ufficiali non sono più scaricabili anonimamente. Per un sistema reale va valutata la provenienza e la manutenzione dell'immagine.

## API essenziali

`POST /api/login` accetta `username` e `password` come form; restituisce un bearer token di 8 ore. `POST /api/documents` (solo admin) accetta `file`, `title` e `roles` separati da virgola. `GET /api/documents` mostra i metadati visibili. `GET /api/documents/{id}` mostra le sezioni solo ai ruoli autorizzati. `POST /api/ask` accetta `{ "question": "..." }`. `GET /api/admin/stats` è riservato all'admin.

## Implementazione per incrementi

1. **Percorso completo**: upload, estrazione, sezioni, embedding, pgvector, risposta estrattiva citata.
2. **Permessi**: JWT per ruolo, filtro SQL, endpoint documento protetto e test di separazione.
3. **Valutazione**: dataset con attesi e astensioni, script ripetibile, soglie di test.
4. **Osservabilità**: span OpenTelemetry, Jaeger, statistiche e limiti configurabili.
