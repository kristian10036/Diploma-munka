# Context-grounded assistant és valódi RAG

A rendszer két, egymásra épülő retrieval módot használ:

1. bounded, paraméterezett SQL-lekérdezés a mérési adatokhoz;
2. opcionális pgvector top-k dokumentum-retrieval.

A publikus assistant státusz külön mutatja:

- `generation`: Ollama generáló komponens;
- `rag`: pgvector retrieval komponens;
- legacy kompatibilitásként `rag_available`, `rag_status` mezők.

A régi hardkódolt `rag_status=not_implemented` eltávolításra került. Lehetséges
RAG státuszok:

```text
disabled
not_configured
database_not_ready
ready_empty
ready
```

A `/api/ask` AI nélkül is visszaadja a strukturált kontextust és a
`source_records` listát. Ollama csak a visszakeresett adatokból készíthet választ.
