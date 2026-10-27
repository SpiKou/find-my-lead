"use client";

import { type ReactNode, useEffect, useRef, useState } from "react";

export function Chevron({ open = false, className = "" }: { open?: boolean; className?: string }) {
  return (
    <svg
      viewBox="0 0 16 16"
      aria-hidden
      className={`size-3.5 shrink-0 transition-transform ${open ? "rotate-180" : ""} ${className}`}
    >
      <path d="M4 6l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

// Κουμπί φίλτρου που ανοίγει πάνελ από κάτω, όπως στο LeadCatalog.
export function FilterMenu({
  label,
  count = 0,
  children,
  wide = false,
}: {
  label: string;
  count?: number;
  children: ReactNode;
  wide?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      if (!ref.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className={`flex h-10 items-center gap-2 rounded-lg border bg-paper px-3 text-sm transition-colors hover:border-ink-soft ${
          open || count ? "border-ink" : "border-line-strong"
        }`}
      >
        {label}
        {count > 0 && (
          <span className="grid min-w-5 place-items-center rounded bg-brand px-1 text-xs font-semibold text-white">
            {count}
          </span>
        )}
        <Chevron open={open} />
      </button>
      {open && (
        <div
          className={`absolute left-0 top-[calc(100%+0.5rem)] z-30 max-h-[min(470px,65vh)] overflow-y-auto rounded-xl border border-line-strong bg-paper p-1.5 shadow-lg ${
            wide ? "w-[min(22rem,calc(100vw-2rem))]" : "w-60"
          }`}
        >
          {children}
        </div>
      )}
    </div>
  );
}

export function Checkbox({
  checked,
  indeterminate = false,
  disabled = false,
  onChange,
  children,
}: {
  checked: boolean;
  indeterminate?: boolean;
  disabled?: boolean;
  onChange: () => void;
  children: ReactNode;
}) {
  return (
    <label
      className={`flex min-h-10 flex-1 items-center gap-3 rounded-md px-2.5 py-2 text-sm ${
        disabled ? "cursor-not-allowed text-muted" : "cursor-pointer hover:bg-brand-soft"
      }`}
    >
      <input
        type="checkbox"
        className="size-4 shrink-0 accent-brand"
        checked={checked}
        disabled={disabled}
        ref={(el) => {
          if (el) el.indeterminate = indeterminate && !checked;
        }}
        onChange={onChange}
      />
      <span className="min-w-0">{children}</span>
    </label>
  );
}

export type Option = { value: string; label: string };

export function Checklist({
  options,
  selected,
  available,
  onChange,
}: {
  options: Option[];
  selected: string[];
  available?: string[];
  onChange: (selected: string[]) => void;
}) {
  return (
    <div>
      {options.map((option) => {
        const checked = selected.includes(option.value);
        const disabled = !checked && available !== undefined && !available.includes(option.value);
        return (
          <Checkbox
            key={option.value}
            checked={checked}
            disabled={disabled}
            onChange={() =>
              onChange(checked ? selected.filter((v) => v !== option.value) : [...selected, option.value])
            }
          >
            {option.label}
            {disabled && <span className="ml-1.5 text-xs">· μετά τον έλεγχο websites</span>}
          </Checkbox>
        );
      })}
    </div>
  );
}

export type TreeOption = Option & { children: Option[] };

// Λίστα δύο επιπέδων (κλάδοι → κατηγορίες, περιφέρειες → πόλεις).
// Ένας επιλεγμένος γονέας καλύπτει όλα τα παιδιά του.
export function TreeChecklist({
  title,
  options,
  parents,
  selectedChildren: children,
  onChange,
}: {
  title: string;
  options: TreeOption[];
  parents: string[];
  selectedChildren: string[];
  onChange: (parents: string[], children: string[]) => void;
}) {
  const [expanded, setExpanded] = useState<string | null>(null);

  const toggleParent = (option: TreeOption) => {
    const childValues = new Set(option.children.map((c) => c.value));
    const otherChildren = children.filter((c) => !childValues.has(c));
    if (parents.includes(option.value)) {
      onChange(parents.filter((p) => p !== option.value), otherChildren);
    } else {
      onChange([...parents, option.value], otherChildren);
    }
  };

  const toggleChild = (option: TreeOption, child: string) => {
    if (parents.includes(option.value)) {
      const rest = option.children.map((c) => c.value).filter((c) => c !== child);
      onChange(parents.filter((p) => p !== option.value), [...children, ...rest]);
      return;
    }
    if (children.includes(child)) {
      onChange(parents, children.filter((c) => c !== child));
      return;
    }
    const next = [...children, child];
    const all = option.children.every((c) => next.includes(c.value));
    if (all) {
      const childValues = new Set(option.children.map((c) => c.value));
      onChange([...parents, option.value], next.filter((c) => !childValues.has(c)));
    } else {
      onChange(parents, next);
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between px-2.5 pb-2 pt-1.5">
        <span className="text-sm font-semibold">{title}</span>
        <span className="flex gap-3 text-sm">
          <button
            type="button"
            className="font-medium text-brand hover:underline"
            onClick={() => onChange(options.map((o) => o.value), [])}
          >
            Όλα
          </button>
          <button type="button" className="text-ink-soft hover:underline" onClick={() => onChange([], [])}>
            Κανένα
          </button>
        </span>
      </div>
      {options.map((option) => {
        const checked = parents.includes(option.value);
        const someChildren = option.children.some((c) => children.includes(c.value));
        const isOpen = expanded === option.value;
        return (
          <div key={option.value} className="border-t border-line">
            <div className="flex items-center">
              <Checkbox checked={checked} indeterminate={someChildren} onChange={() => toggleParent(option)}>
                {option.label}
              </Checkbox>
              {option.children.length > 0 && (
                <button
                  type="button"
                  aria-label={`Εμφάνιση: ${option.label}`}
                  aria-expanded={isOpen}
                  className="grid size-9 shrink-0 place-items-center rounded-md text-ink-soft hover:bg-brand-soft"
                  onClick={() => setExpanded(isOpen ? null : option.value)}
                >
                  <Chevron open={isOpen} />
                </button>
              )}
            </div>
            {isOpen && (
              <div className="mb-1 ml-6 border-l border-line pl-1">
                {option.children.map((child) => (
                  <Checkbox
                    key={child.value}
                    checked={checked || children.includes(child.value)}
                    onChange={() => toggleChild(option, child.value)}
                  >
                    {child.label}
                  </Checkbox>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
