# Find My Lead

Προσωπική replica του leadcatalog.app: κατάλογος ελληνικών επιχειρήσεων με φίλτρα
ανά κλάδο, περιοχή, κατάσταση website, τεχνολογία, e-shop και Lighthouse scores,
με εξαγωγή σε CSV.

## Αρχιτεκτονική

- `pipeline/`: Python + DuckDB. Παίρνει τα Overture Places, αντιστοιχίζει δήμο και
  περιφέρεια, κανονικοποιεί, ενώνει διπλές εγγραφές, βάζει κλάδους και φορτώνει
  στη βάση. Τρέχει στο GitHub Actions (workflow «Data pipeline»).
- Βάση: Postgres στο Neon.
- `web/`: Next.js στο Vercel, με τα φίλτρα του `docs/filters.md`.

## Τοπική ανάπτυξη

```bash
brew install postgresql@17 && brew services start postgresql@17
createdb findmylead
DATABASE_URL=postgresql://localhost/findmylead uv run python pipeline/load_db.py
echo "DATABASE_URL=postgresql://localhost/findmylead" > web/.env.local
npm --prefix web run dev
```

Το `load_db.py` χρειάζεται τα αρχεία του `data/staging/` (από τοπικό τρέξιμο του
pipeline ή από το artifact του workflow). Με βάση στο localhost το site χρησιμοποιεί
το node-postgres αντί για τον HTTP driver του Neon.
