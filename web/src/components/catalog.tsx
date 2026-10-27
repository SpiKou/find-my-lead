"use client";

import { usePathname, useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { BusinessRowCard } from "@/components/business-row";
import { Checklist, FilterMenu, TreeChecklist } from "@/components/filter-menu";
import { SearchBox } from "@/components/search-box";
import type { BusinessRow, FilterOptions } from "@/lib/catalog";
import {
  CONTACT_OPTIONS,
  type Filters,
  QUALITY_OPTIONS,
  TECHNOLOGIES,
  WEBSITE_OPTIONS,
  emptyFilters,
  splitCity,
  toSearchParams,
} from "@/lib/filters";

type Chip = { key: string; label: string; remove: (f: Filters) => Filters };

function activeChips(filters: Filters, options: FilterOptions): Chip[] {
  const industryLabel = new Map(options.industries.map((i) => [i.value, i.label]));
  const typeLabel = new Map(options.industries.flatMap((i) => i.types.map((t) => [t.value, t.label])));
  const labelOf = (list: { value: string; label: string }[], value: string) =>
    list.find((o) => o.value === value)?.label ?? value;
  const without = (list: string[], value: string) => list.filter((v) => v !== value);

  return [
    ...(filters.q ? [{ key: "q", label: `Όνομα: ${filters.q}`, remove: (f: Filters) => ({ ...f, q: "" }) }] : []),
    ...filters.industries.map((v) => ({
      key: `industry:${v}`,
      label: `Κλάδος: ${industryLabel.get(v) ?? v}`,
      remove: (f: Filters) => ({ ...f, industries: without(f.industries, v) }),
    })),
    ...filters.types.map((v) => ({
      key: `type:${v}`,
      label: `Κατηγορία: ${typeLabel.get(v) ?? v}`,
      remove: (f: Filters) => ({ ...f, types: without(f.types, v) }),
    })),
    ...filters.regions.map((v) => ({
      key: `region:${v}`,
      label: `Περιοχή: ${v}`,
      remove: (f: Filters) => ({ ...f, regions: without(f.regions, v) }),
    })),
    ...filters.cities.map((v) => ({
      key: `city:${v}`,
      label: `Πόλη: ${splitCity(v)[1]}`,
      remove: (f: Filters) => ({ ...f, cities: without(f.cities, v) }),
    })),
    ...filters.website.map((v) => ({
      key: `website:${v}`,
      label: `Website: ${labelOf(WEBSITE_OPTIONS, v)}`,
      remove: (f: Filters) => ({ ...f, website: without(f.website, v) }),
    })),
    ...filters.quality.map((v) => ({
      key: `quality:${v}`,
      label: labelOf(QUALITY_OPTIONS, v),
      remove: (f: Filters) => ({ ...f, quality: without(f.quality, v) }),
    })),
    ...filters.contact.map((v) => ({
      key: `contact:${v}`,
      label: `Επικοινωνία: ${labelOf(CONTACT_OPTIONS, v)}`,
      remove: (f: Filters) => ({ ...f, contact: without(f.contact, v) }),
    })),
    ...filters.tech.map((v) => ({
      key: `tech:${v}`,
      label: `Τεχνολογία: ${v}`,
      remove: (f: Filters) => ({ ...f, tech: without(f.tech, v) }),
    })),
    ...(filters.eshop ? [{ key: "eshop", label: "E-shop", remove: (f: Filters) => ({ ...f, eshop: false }) }] : []),
  ];
}

export function Catalog({
  options,
  filters,
  results,
}: {
  options: FilterOptions;
  filters: Filters;
  results: { rows: BusinessRow[]; total: number } | null;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [isPending, startTransition] = useTransition();

  const update = (next: Filters) => {
    const query = toSearchParams(next).toString();
    startTransition(() => {
      router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
    });
  };

  const chips = activeChips(filters, options);
  const query = toSearchParams(filters).toString();
  const techOptions = TECHNOLOGIES.map((t) => ({ value: t, label: t }));

  return (
    <div className="flex flex-col gap-4">
      <SearchBox options={options} filters={filters} onChange={update} />

      <div className="flex flex-wrap gap-2">
        <FilterMenu label="Κλάδος" count={filters.industries.length + filters.types.length} wide>
          <TreeChecklist
            title="Κλάδος"
            options={options.industries.map((i) => ({ ...i, children: i.types }))}
            parents={filters.industries}
            selectedChildren={filters.types}
            onChange={(industries, types) => update({ ...filters, industries, types })}
          />
        </FilterMenu>
        <FilterMenu label="Τοποθεσία" count={filters.regions.length + filters.cities.length} wide>
          <TreeChecklist
            title="Τοποθεσία"
            options={options.regions.map((r) => ({ ...r, children: r.cities }))}
            parents={filters.regions}
            selectedChildren={filters.cities}
            onChange={(regions, cities) => update({ ...filters, regions, cities })}
          />
        </FilterMenu>
        <FilterMenu label="Website" count={filters.website.length}>
          <Checklist
            options={WEBSITE_OPTIONS}
            selected={filters.website}
            available={options.available.website}
            onChange={(website) => update({ ...filters, website })}
          />
        </FilterMenu>
        <FilterMenu label="Τεχνική κατάσταση" count={filters.quality.length}>
          <Checklist
            options={QUALITY_OPTIONS}
            selected={filters.quality}
            available={options.available.quality}
            onChange={(quality) => update({ ...filters, quality })}
          />
        </FilterMenu>
        <FilterMenu label="Επικοινωνία" count={filters.contact.length}>
          <Checklist
            options={CONTACT_OPTIONS}
            selected={filters.contact}
            onChange={(contact) => update({ ...filters, contact })}
          />
        </FilterMenu>
        <FilterMenu label="Τεχνολογία" count={filters.tech.length}>
          <Checklist
            options={techOptions}
            selected={filters.tech}
            available={options.available.tech}
            onChange={(tech) => update({ ...filters, tech })}
          />
        </FilterMenu>
        <button
          type="button"
          disabled={!options.available.eshop && !filters.eshop}
          title={options.available.eshop ? undefined : "Διαθέσιμο μετά τον έλεγχο websites"}
          onClick={() => update({ ...filters, eshop: !filters.eshop })}
          className={`h-10 rounded-lg border bg-paper px-3 text-sm transition-colors enabled:hover:border-ink-soft disabled:cursor-not-allowed disabled:text-muted ${
            filters.eshop ? "border-ink bg-brand-soft" : "border-line-strong"
          }`}
        >
          E-shop
        </button>
      </div>

      {chips.length > 0 && (
        <div className="flex items-start gap-3">
          <span className="mt-2 text-xs text-muted">Ενεργά</span>
          <div className="flex flex-1 flex-wrap gap-2">
            {chips.map((chip) => (
              <span
                key={chip.key}
                className="flex h-8 items-center gap-2 rounded-lg border border-line-strong bg-paper pl-2.5 text-xs"
              >
                {chip.label}
                <button
                  type="button"
                  aria-label={`Αφαίρεση: ${chip.label}`}
                  className="grid h-full w-7 place-items-center border-l border-line text-ink-soft hover:text-ink"
                  onClick={() => update(chip.remove(filters))}
                >
                  ×
                </button>
              </span>
            ))}
          </div>
          <button
            type="button"
            className="mt-2 shrink-0 text-xs text-ink-soft hover:underline"
            onClick={() => update(emptyFilters())}
          >
            Καθαρισμός όλων
          </button>
        </div>
      )}

      <div className={`transition-opacity ${isPending ? "opacity-50" : ""}`} aria-busy={isPending}>
        {results ? (
          <Results key={query} query={query} initialRows={results.rows} total={results.total} />
        ) : (
          <div className="mt-2 flex gap-3 rounded-xl border border-dashed border-line-strong px-5 py-5">
            <svg viewBox="0 0 20 20" aria-hidden className="mt-0.5 size-4 shrink-0 text-brand">
              <circle cx="9" cy="9" r="5.5" fill="none" stroke="currentColor" strokeWidth="1.7" />
              <path d="M13.2 13.2L17 17" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
            </svg>
            <div>
              <p className="text-sm font-medium">Βρες επιχειρήσεις με τα δικά σου κριτήρια</p>
              <p className="text-xs text-muted">
                Χρησιμοποίησε την αναζήτηση ή τα φίλτρα παραπάνω για να εμφανιστούν τα πρώτα αποτελέσματα.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Results({ query, initialRows, total }: { query: string; initialRows: BusinessRow[]; total: number }) {
  const [rows, setRows] = useState(initialRows);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  const loadMore = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams(query);
      params.set("offset", String(rows.length));
      const response = await fetch(`/api/businesses?${params}`);
      const data: { rows: BusinessRow[] } = await response.json();
      setRows((current) => [...current, ...data.rows]);
    } finally {
      setLoading(false);
    }
  };

  const share = async () => {
    await navigator.clipboard.writeText(window.location.href);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <section className="mt-2">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-semibold">
          {total.toLocaleString("el-GR")} {total === 1 ? "αποτέλεσμα" : "αποτελέσματα"}
        </h2>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={share}
            className="h-10 rounded-lg border border-line-strong bg-paper px-4 text-sm hover:border-ink-soft"
          >
            {copied ? "Ο σύνδεσμος αντιγράφηκε" : "Κοινοποίηση αναζήτησης"}
          </button>
          <a
            href={`/api/export?${query}`}
            className="flex h-10 items-center rounded-lg bg-brand px-4 text-sm font-medium text-white hover:bg-brand-strong"
          >
            Εξαγωγή CSV
          </a>
        </div>
      </div>

      {total === 0 ? (
        <p className="rounded-xl border border-line bg-paper px-5 py-6 text-sm text-ink-soft">
          Δεν βρέθηκαν επιχειρήσεις με αυτά τα κριτήρια.
        </p>
      ) : (
        <>
          <div className="hidden px-4 pb-2 text-xs text-muted md:grid md:grid-cols-[1.3fr_1fr_0.9fr_1.2fr] md:gap-x-6">
            <span>Επιχείρηση</span>
            <span>Κατηγορία επιχείρησης</span>
            <span>Περιοχή</span>
            <span>Επικοινωνία</span>
          </div>
          <ul className="flex flex-col gap-2">
            {rows.map((row) => (
              <BusinessRowCard key={row.id} row={row} />
            ))}
          </ul>
          {rows.length < total && (
            <div className="mt-6 flex flex-col items-center gap-2">
              <button
                type="button"
                onClick={loadMore}
                disabled={loading}
                className="h-10 rounded-lg border border-line-strong bg-paper px-5 text-sm hover:border-ink-soft disabled:opacity-60"
              >
                {loading ? "Φόρτωση…" : "Φόρτωση περισσότερων"}
              </button>
              <p className="text-xs text-muted">
                {rows.length.toLocaleString("el-GR")} από {total.toLocaleString("el-GR")}
              </p>
            </div>
          )}
        </>
      )}
    </section>
  );
}
