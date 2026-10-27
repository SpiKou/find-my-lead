// Τα φίλτρα του καταλόγου (docs/filters.md) και η μετατροπή τους από/προς URL.
// Χρησιμοποιείται και από τον server και από τον browser.

export type Filters = {
  q: string;
  industries: string[];
  types: string[];
  regions: string[];
  cities: string[];
  website: string[];
  quality: string[];
  contact: string[];
  tech: string[];
  eshop: boolean;
};

// Κλάδος για τις επιχειρήσεις χωρίς σαφή κατηγορία (industry IS NULL).
export const UNCATEGORIZED = "uncategorized";

// Μια πόλη αποθηκεύεται ως "περιφέρεια|πόλη", γιατί πολλά χωριά έχουν ίδιο όνομα.
export const CITY_SEPARATOR = "|";

export const WEBSITE_OPTIONS = [
  { value: "active", label: "Ενεργό" },
  { value: "inactive", label: "Ανενεργό" },
  { value: "none", label: "Χωρίς website" },
  { value: "unknown", label: "Μη ελεγμένο" },
];

export const QUALITY_OPTIONS = [
  { value: "weak", label: "Τεχνικές αδυναμίες" },
  { value: "lowseo", label: "Χαμηλό SEO score" },
];

export const CONTACT_OPTIONS = [
  { value: "email", label: "Email" },
  { value: "phone", label: "Τηλέφωνο" },
  { value: "social", label: "Social profiles" },
];

export const TECHNOLOGIES = [
  "WordPress",
  "WooCommerce",
  "Joomla",
  "OpenCart",
  "Wix",
  "Shopify",
  "Next.js",
  "PrestaShop",
  "Drupal",
  "Magento",
  "Angular",
  "Squarespace",
  "Webflow",
  "Nuxt",
  "React",
  "Vue",
];

const LIST_PARAMS = {
  industries: "industry",
  types: "type",
  regions: "region",
  cities: "city",
  website: "website",
  quality: "quality",
  contact: "contact",
  tech: "tech",
} as const;

type ListKey = keyof typeof LIST_PARAMS;
type RawParams = URLSearchParams | Record<string, string | string[] | undefined>;

function getAll(params: RawParams, key: string): string[] {
  if (params instanceof URLSearchParams) return params.getAll(key);
  const value = params[key];
  if (value === undefined) return [];
  return Array.isArray(value) ? value : [value];
}

export function parseFilters(params: RawParams): Filters {
  const filters = {
    q: (getAll(params, "q")[0] ?? "").trim(),
    eshop: getAll(params, "eshop")[0] === "1",
  } as Filters;
  for (const [key, param] of Object.entries(LIST_PARAMS) as [ListKey, string][]) {
    filters[key] = [...new Set(getAll(params, param).filter(Boolean))];
  }
  return filters;
}

export function toSearchParams(filters: Filters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.q) params.set("q", filters.q);
  for (const [key, param] of Object.entries(LIST_PARAMS) as [ListKey, string][]) {
    for (const value of filters[key]) params.append(param, value);
  }
  if (filters.eshop) params.set("eshop", "1");
  return params;
}

export function hasFilters(filters: Filters): boolean {
  return toSearchParams(filters).size > 0;
}

export function emptyFilters(): Filters {
  return parseFilters(new URLSearchParams());
}

export function cityValue(region: string, city: string): string {
  return `${region}${CITY_SEPARATOR}${city}`;
}

export function splitCity(value: string): [region: string, city: string] {
  const at = value.indexOf(CITY_SEPARATOR);
  return at < 0 ? ["", value] : [value.slice(0, at), value.slice(at + 1)];
}

// Ίδια κανονικοποίηση με το name_search του pipeline (normalize.py):
// πεζά, χωρίς τόνους, μονά κενά.
export function normalizeSearch(text: string): string {
  return text
    .toLowerCase()
    .normalize("NFKD")
    .replace(/\p{M}/gu, "")
    .replace(/\s+/g, " ")
    .trim();
}
