# NIC Operator Guide — West Tripura Citizen RAG

This guide is for an NIC/operator who needs to run, refresh, test, and troubleshoot the local West Tripura RAG chatbot.

## 1. System overview

```text
Official West Tripura website
        ↓
Crawl4AI
        ↓
Pages + official document links
        ↓
Download/extract documents
        ↓
Preprocess + metadata
        ↓
Semantic chunks
        ↓
Embeddings
        ↓
Pinecone + BM25
        ↓
Citizen RAG API
        ↓
Telegram / WhatsApp / local API
```

## 2. First-time setup

```bash
git clone https://github.com/bappaditya-paul/west-tripura-testing.git
cd west-tripura-testing
cp .env.example .env
```

Fill the required credentials in `.env`.

For the lightweight API:

```bash
pip install -r requirements.txt
```

For crawling/document ingestion:

```bash
pip install -r requirements-ingestion.txt
```

## 3. Refresh the official knowledge base

Run:

```bash
python src/ingestion/auto_ingest.py
```

This performs:

```text
Crawl4AI
→ materialize official document assets
→ preprocess documents
→ production semantic chunking
→ embeddings
→ Pinecone upsert
```

For a crawl interrupted midway:

```bash
python src/ingestion/auto_ingest.py --resume
```

For a deliberate full vector rebuild:

```bash
python src/ingestion/auto_ingest.py --clear-index
```

Do not use `--clear-index` for a routine refresh unless you intentionally want to replace the current index.

## 4. Verify ingestion before starting the chatbot

Inspect:

```bash
find output/pages -type f | wc -l
find output/documents -type f | wc -l
find processed_documents -type f | wc -l
find processed_chunks -type f -name 'chunk_*.json' | wc -l
```

Review the crawl log:

```bash
tail -n 100 output/crawl.log
```

Verify that important documents are present:

```bash
find output/documents -type f | grep -Ei 'pdf|docx|xlsx|form|notification|certificate|recruitment|tender'
```

## 5. Start the local application

```bash
docker compose up -d
```

Check:

```bash
docker compose ps
```

API logs:

```bash
docker compose logs -f api
```

Telegram logs:

```bash
docker compose logs -f telegram
```

WhatsApp logs:

```bash
docker compose logs -f whatsapp
```

## 6. Test without a phone

Open the FastAPI Swagger UI:

```text
http://localhost:8001/docs
```

Use the RAG chat/query endpoint directly. Test:

```text
Hello
```

```text
DM office er number ta ki?
```

```text
How can I apply for a PRTC and what documents are required?
```

```text
আমি কীভাবে একটি সার্টিফিকেটের জন্য আবেদন করব?
```

```text
Show me the official application form.
```

Also test an unavailable official fact to confirm the system does not invent information.

## 7. What a good document answer looks like

For a query requesting a government form, the ideal response contains:

```text
1. Simple explanation of the procedure
2. Required documents
3. Official source page
4. Direct official document link when available
```

Example:

```text
📄 PRTC application form
🔗 <official PDF URL>
```

## 8. Updating code after a Git merge

```bash
git checkout main
git pull origin main
```

Rebuild the API-related services after code/dependency changes:

```bash
docker compose build --no-cache api telegram whatsapp
docker compose up -d api telegram whatsapp
```

If only the API changed, rebuild only `api`.

## 9. If `auth.docker.io` DNS fails

Test:

```bash
getent hosts auth.docker.io
resolvectl query auth.docker.io
docker pull python:3.12-slim
```

If the host resolver is broken, repair the host DNS first. Once `docker pull python:3.12-slim` succeeds, retry the Compose build.

## 10. If a citizen question returns no useful answer

Use this debugging order:

```text
1. Test `/search` in Swagger
2. Inspect retrieval_query
3. Inspect returned titles/sections/URLs
4. Check whether the required page/document exists in output/
5. Check whether the document was processed into processed_documents/
6. Check whether chunks exist in processed_chunks/
7. Check Pinecone vector count
8. Re-run ingestion if the corpus is stale
```

If a document is absent from the official source, the chatbot should say it could not verify it rather than inventing a form or procedure.

## 11. Runtime data

These directories contain local/generated data and are intentionally ignored by Git:

```text
output/
processed_documents/
processed_chunks/
uploads/
```

Do not commit government document binaries or `.env` secrets.

## 12. Recommended maintenance

When the official district site changes materially:

```bash
python src/ingestion/auto_ingest.py
```

After a refresh, verify:

```text
page count
→ document count
→ chunk count
→ Pinecone count
→ sample citizen queries
```

Keep the previous healthy index available until the new crawl has been checked, especially if the district website is temporarily unavailable.

## 13. Scope and external official services

The district site does not necessarily publish every citizen service or form. For services owned by another official Tripura department, municipality, or e-District system, add the approved official source to the ingestion scope rather than guessing.

The chatbot should always distinguish:

```text
Verified official West Tripura information
vs.
General information
vs.
Not verified
```
