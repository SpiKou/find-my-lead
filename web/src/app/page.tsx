import { Suspense } from "react";
import { Catalog } from "@/components/catalog";
import { getFilterOptions, searchBusinesses } from "@/lib/catalog";
import { getDb } from "@/lib/db";
import { hasFilters, parseFilters } from "@/lib/filters";

async function CatalogSection({ searchParams }: { searchParams: PageProps<"/">["searchParams"] }) {
  const filters = parseFilters(await searchParams);
  if (!getDb()) {
    return <p className="text-ink-soft">Δεν έχει οριστεί DATABASE_URL.</p>;
  }

  const [options, results] = await Promise.all([
    getFilterOptions(),
    hasFilters(filters) ? searchBusinesses(filters) : null,
  ]);

  return (
    <>
      <p className="mb-8 inline-block bg-highlight/70 px-1 text-sm font-medium">
        {options.total.toLocaleString("el-GR")} επιχειρήσεις στη λίστα
      </p>
      <Catalog
        options={options}
        filters={filters}
        results={results && { rows: results.rows, total: results.total ?? 0 }}
      />
    </>
  );
}

export default function Home({ searchParams }: PageProps<"/">) {
  return (
    <>
      <header className="border-b border-line bg-paper">
        <div className="mx-auto flex h-14 w-full max-w-6xl items-center px-4">
          <span className="font-semibold tracking-tight text-brand">Find My Lead</span>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl px-4 pb-16 pt-10">
        <h1 className="max-w-2xl text-3xl font-semibold leading-tight tracking-tight sm:text-4xl">
          Βρες ελληνικές επιχειρήσεις. Φτιάξε τη λίστα υποψήφιων πελατών σου.
        </h1>
        <p className="mb-3 mt-3 max-w-2xl text-sm text-ink-soft">
          Φίλτραρε ανά κλάδο, περιοχή, κατάσταση website και στοιχεία επικοινωνίας και εξήγαγε τη λίστα σε CSV.
        </p>
        <Suspense fallback={<p className="text-sm text-muted">Φόρτωση…</p>}>
          <CatalogSection searchParams={searchParams} />
        </Suspense>
      </main>
    </>
  );
}
