# Valódi RAG és offline Ollama

A webes kezelőfelület külön **RAG** lapja a Spectrum főoldal navigációjából érhető el. Az import oldal kizárólag adat- és referenciaimportra szolgál.

A RAG nem „buta AI” és nem önálló nyelvi modell. A feladata, hogy a kérdéshez
releváns dokumentumrészeket keressen ki, majd ezeket átadja egy generáló modellnek.

## Pipeline

```text
dokumentum → chunk → embedding → pgvector HNSW
a kérdés → embedding → top-k chunk
SQL mérési context + top-k chunk → Ollama → forrásolt válasz
```

## Embedding providerek

- `local_hash`: teljesen offline, determinisztikus baseline; tesztelésre és
  lexikai hasonlóságra jó, szemantikailag korlátozott.
- `ollama`: neurális embeddingmodell az Ollama `/api/embed` végpontján.

## Okosabb offline beállítás

A chatmodell és az embeddingmodell külön konfigurálható:

```env
AI_ENABLED=true
OLLAMA_URL=http://ollama:11434
OLLAMA_MODEL=qwen3:8b
OLLAMA_TIMEOUT_SECONDS=300
RAG_ENABLED=true
RAG_EMBEDDING_PROVIDER=ollama
RAG_EMBEDDING_MODEL=bge-m3
```

A konkrét chatmodell a célgép RAM/GPU kapacitásához cserélhető. Nagyobb modell
általában jobb következtetést ad, de több memóriát és időt igényel. A rendszer
nem függ egyetlen modelltől.

Modellek letöltése:

```bash
bash scripts/ollama-setup.sh
```

Embeddingmodell-váltás után a dokumentumokat újra kell indexelni; eltérő
embeddingterek vektorai nem keverhetők.

A rendszer provider/modell/dimenzió profilt tárol. A `bge-m3` 1024 dimenziós
indexet használ; a korábbi 768 dimenziós rekordok megmaradnak, de nem kerülnek
egy keresésbe. A `/api/rag/status` `index_compatible` és `reindex_required`
mezői jelzik az újraindexelési igényt. Az Ollama embedding hívás a
`POST /api/embed` végpontot használja batch inputtal, korlátozott retryjal.

## Státusz

```text
GET  /api/rag/status
GET  /api/assistant/status
POST /api/rag/documents
POST /api/rag/retrieve
POST /api/ask
```

A `rag=true` csak akkor jelenik meg a válaszban, ha valódi dokumentumchunk került
vissza. Az index implementált lehet úgy is, hogy futás közben `disabled` vagy
`ready_empty`.
