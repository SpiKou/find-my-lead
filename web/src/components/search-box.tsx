"use client";

import { useMemo, useState } from "react";
import type { FilterOptions } from "@/lib/catalog";
import { type Filters, TECHNOLOGIES, normalizeSearch } from "@/lib/filters";

type Suggestion = {
  group: string;
  label: string;
  detail?: string;
  apply: (filters: Filters) => Filters;
};

const MAX_PER_GROUP = 6;

function add(list: string[], value: string) {
  return list.includes(value) ? list : [...list, value];
}

function buildSuggestions(options: FilterOptions): Suggestion[] {
  const suggestions: Suggestion[] = [];
  for (const industry of options.industries) {
    suggestions.push({
      group: "Κλάδος",
      label: industry.label,
      apply: (f) => ({ ...f, industries: add(f.industries, industry.value) }),
    });
    for (const type of industry.types) {
      suggestions.push({
        group: "Κατηγορία",
        label: type.label,
        detail: industry.label,
        apply: (f) => ({ ...f, types: add(f.types, type.value) }),
      });
    }
  }
  for (const region of options.regions) {
    suggestions.push({
      group: "Περιφέρεια",
      label: region.label,
      apply: (f) => ({ ...f, regions: add(f.regions, region.value) }),
    });
  }
  for (const region of options.regions) {
    for (const city of region.cities) {
      suggestions.push({
        group: "Πόλη",
        label: city.label,
        detail: region.label,
        apply: (f) => ({ ...f, cities: add(f.cities, city.value) }),
      });
    }
  }
  for (const tech of TECHNOLOGIES.filter((t) => options.available.tech.includes(t))) {
    suggestions.push({ group: "Τεχνολογία", label: tech, apply: (f) => ({ ...f, tech: add(f.tech, tech) }) });
  }
  return suggestions;
}

// Αναζήτηση που προτείνει φίλτρα (κλάδο, κατηγορία, περιφέρεια, πόλη,
// τεχνολογία) ή αναζήτηση στο όνομα της επιχείρησης.
export function SearchBox({
  options,
  filters,
  onChange,
}: {
  options: FilterOptions;
  filters: Filters;
  onChange: (filters: Filters) => void;
}) {
  const [text, setText] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const all = useMemo(() => buildSuggestions(options), [options]);

  const query = normalizeSearch(text);
  const matches = useMemo(() => {
    if (!query) return [];
    const nameSearch: Suggestion = {
      group: "Επιχείρηση",
      label: `Όνομα που περιέχει «${text.trim()}»`,
      apply: (f) => ({ ...f, q: text.trim() }),
    };
    const perGroup = new Map<string, number>();
    const found = all.filter((s) => {
      if (!normalizeSearch(s.label).includes(query)) return false;
      const n = perGroup.get(s.group) ?? 0;
      perGroup.set(s.group, n + 1);
      return n < MAX_PER_GROUP;
    });
    return [...found, nameSearch];
  }, [all, query, text]);

  const choose = (suggestion: Suggestion) => {
    onChange(suggestion.apply(filters));
    setText("");
    setOpen(false);
  };

  const groups = matches.reduce<{ group: string; items: { s: Suggestion; index: number }[] }[]>(
    (acc, s, index) => {
      const last = acc[acc.length - 1];
      if (last?.group === s.group) last.items.push({ s, index });
      else acc.push({ group: s.group, items: [{ s, index }] });
      return acc;
    },
    [],
  );

  return (
    <div className="relative">
      <svg viewBox="0 0 20 20" aria-hidden className="pointer-events-none absolute left-4 top-1/2 size-4 -translate-y-1/2 text-ink-soft">
        <circle cx="9" cy="9" r="5.5" fill="none" stroke="currentColor" strokeWidth="1.7" />
        <path d="M13.2 13.2L17 17" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
      </svg>
      <input
        type="search"
        value={text}
        placeholder="Αναζήτηση κλάδου, κατηγορίας, περιφέρειας, πόλης, τεχνολογίας ή επιχείρησης"
        aria-label="Αναζήτηση"
        role="combobox"
        aria-expanded={open && matches.length > 0}
        aria-controls="search-suggestions"
        className="h-12 w-full rounded-xl border border-line-strong bg-paper pl-11 pr-4 text-sm outline-none placeholder:text-muted focus:border-ink"
        onChange={(e) => {
          setText(e.target.value);
          setActive(0);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={(e) => {
          if (!matches.length) return;
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setActive((active + 1) % matches.length);
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActive((active - 1 + matches.length) % matches.length);
          } else if (e.key === "Enter") {
            e.preventDefault();
            choose(matches[active]);
          } else if (e.key === "Escape") {
            setOpen(false);
          }
        }}
      />
      {open && matches.length > 0 && (
        <div
          id="search-suggestions"
          role="listbox"
          className="absolute inset-x-0 top-[calc(100%+0.5rem)] z-40 max-h-[min(470px,65vh)] overflow-y-auto rounded-xl border border-line-strong bg-paper p-1.5 shadow-lg"
        >
          {groups.map(({ group, items }) => (
            <div key={group} role="group" aria-label={group} className="pb-1 [&+div]:mt-2">
              <p className="mb-1 rounded-md bg-canvas px-3 py-2 text-xs font-semibold text-ink-soft">{group}</p>
              {items.map(({ s, index }) => (
                <button
                  key={`${s.group}:${s.label}:${s.detail ?? ""}`}
                  type="button"
                  role="option"
                  aria-selected={index === active}
                  className={`flex min-h-10 w-full items-baseline gap-2 rounded-md px-3 py-2 text-left text-sm hover:bg-brand-soft ${
                    index === active ? "bg-brand-soft" : ""
                  }`}
                  onMouseEnter={() => setActive(index)}
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => choose(s)}
                >
                  <strong className="truncate font-medium">{s.label}</strong>
                  {s.detail && <span className="shrink-0 truncate text-muted">{s.detail}</span>}
                </button>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
