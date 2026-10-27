// Ερωτήματα του καταλόγου στον πίνακα businesses (μόνο στον server).

import { cacheLife } from "next/cache";
import { getDb } from "@/lib/db";
import { type Filters, UNCATEGORIZED, cityValue, normalizeSearch, splitCity } from "@/lib/filters";

export const PAGE_SIZE = 20;

// Πόλεις με λιγότερες επιχειρήσεις δεν εμφανίζονται στο φίλτρο Τοποθεσία.
const MIN_CITY_BUSINESSES = 10;

export type BusinessRow = {
  id: string;
  name: string;
  website: string | null;
  website_status: string;
  business_type_name: string;
  industry_name: string | null;
  city: string | null;
  region: string | null;
  locations_count: number;
  emails: string[];
  phones: string[];
  socials: string[];
  social_platforms: string[];
  eshop: boolean | null;
};

export type FilterOptions = {
  total: number;
  release: string;
  industries: { value: string; label: string; types: { value: string; label: string }[] }[];
  regions: { value: string; label: string; cities: { value: string; label: string }[] }[];
  // Τιμές που υπάρχουν στα δεδομένα· οι υπόλοιπες επιλογές εμφανίζονται ανενεργές.
  available: {
    website: string[];
    quality: string[];
    tech: string[];
    eshop: boolean;
  };
};

type Where = { clause: string; params: unknown[] };

function buildWhere(filters: Filters): Where {
  const params: unknown[] = [];
  const param = (value: unknown) => {
    params.push(value);
    return `$${params.length}`;
  };
  const groups: string[] = [];
  const anyOf = (conditions: string[]) => {
    if (conditions.length) groups.push(`(${conditions.join(" OR ")})`);
  };

  const q = normalizeSearch(filters.q);
  if (q) {
    groups.push(`search_name LIKE ${param(`%${q.replace(/[\\%_]/g, "\\$&")}%`)}`);
  }

  const industries = filters.industries.filter((i) => i !== UNCATEGORIZED);
  anyOf([
    ...(industries.length ? [`industry = ANY(${param(industries)})`] : []),
    ...(filters.industries.includes(UNCATEGORIZED) ? ["industry IS NULL"] : []),
    ...(filters.types.length ? [`business_type = ANY(${param(filters.types)})`] : []),
  ]);

  anyOf([
    ...(filters.regions.length ? [`administrative_areas && ${param(filters.regions)}::varchar[]`] : []),
    ...filters.cities.map((value) => {
      const [region, city] = splitCity(value);
      return `(administrative_areas @> ARRAY[${param(region)}]::varchar[] AND localities @> ARRAY[${param(city)}]::varchar[])`;
    }),
  ]);

  if (filters.website.length) groups.push(`website_status = ANY(${param(filters.website)})`);

  anyOf([
    ...(filters.quality.includes("weak") ? ["has_technical_weaknesses"] : []),
    ...(filters.quality.includes("lowseo") ? ["has_low_seo"] : []),
  ]);

  anyOf([
    ...(filters.contact.includes("email") ? ["has_email"] : []),
    ...(filters.contact.includes("phone") ? ["has_phone"] : []),
    ...(filters.contact.includes("social") ? ["has_social"] : []),
  ]);

  if (filters.tech.length) groups.push(`technologies && ${param(filters.tech)}::varchar[]`);
  if (filters.eshop) groups.push("eshop");

  return { clause: groups.length ? `WHERE ${groups.join(" AND ")}` : "", params };
}

function requireDb() {
  const db = getDb();
  if (!db) throw new Error("Δεν έχει οριστεί DATABASE_URL.");
  return db;
}

const RESULT_COLUMNS = `
  id, name, website, website_status, business_type_name, industry_name,
  localities[1] AS city, administrative_areas[1] AS region, locations_count,
  emails, phones, socials, social_platforms, eshop`;

export async function searchBusinesses(filters: Filters, offset = 0) {
  const db = requireDb();
  const { clause, params } = buildWhere(filters);
  const [rows, [{ total }]] = await Promise.all([
    db.query(
      `SELECT ${RESULT_COLUMNS} FROM businesses ${clause}
       ORDER BY search_name COLLATE "C", id LIMIT ${PAGE_SIZE} OFFSET ${Math.max(0, Math.floor(offset))}`,
      params,
    ),
    offset === 0
      ? db.query(`SELECT count(*)::int AS total FROM businesses ${clause}`, params)
      : Promise.resolve([{ total: null }]),
  ]);
  return { rows: rows as BusinessRow[], total: total as number | null };
}

// Οι 20 στήλες της εξαγωγής CSV, όπως στο LeadCatalog (docs/filters.md).
export const EXPORT_COLUMNS = [
  "business_name",
  "business_type",
  "industry",
  "website",
  "website_status",
  "emails",
  "phones",
  "social_urls",
  "locations",
  "locality",
  "administrative_area",
  "locations_count",
  "technologies",
  "eshop",
  "has_technical_weaknesses",
  "has_low_seo",
  "lighthouse_performance",
  "lighthouse_accessibility",
  "lighthouse_best_practices",
  "lighthouse_seo",
] as const;

const EXPORT_SELECT = `
  id, search_name, name AS business_name, business_type_name AS business_type, industry_name AS industry,
  website, website_status, emails, phones, socials AS social_urls, locations,
  localities AS locality, administrative_areas AS administrative_area, locations_count,
  technologies, eshop, has_technical_weaknesses, has_low_seo, lighthouse_performance,
  lighthouse_accessibility, lighthouse_best_practices, lighthouse_seo`;

// Διαβάζει όλα τα αποτελέσματα σε κομμάτια (keyset στο search_name, id),
// ώστε η εξαγωγή να μη φορτώνει όλο τον πίνακα στη μνήμη.
export async function* exportBusinesses(filters: Filters, batchSize = 2000) {
  const db = requireDb();
  const { clause, params } = buildWhere(filters);
  let after: { search_name: string; id: string } | null = null;
  while (true) {
    const keyParams: unknown[] = after ? [...params, after.search_name, after.id] : params;
    let where = clause;
    if (after) {
      const keyset = `(search_name COLLATE "C", id) > ($${params.length + 1}, $${params.length + 2})`;
      where = clause ? `${clause} AND ${keyset}` : `WHERE ${keyset}`;
    }
    const rows = (await db.query(
      `SELECT ${EXPORT_SELECT} FROM businesses ${where} ORDER BY search_name COLLATE "C", id LIMIT ${batchSize}`,
      keyParams,
    )) as Record<string, unknown>[];
    if (rows.length === 0) return;
    yield rows;
    if (rows.length < batchSize) return;
    const last = rows[rows.length - 1];
    after = { search_name: last.search_name as string, id: last.id as string };
  }
}

export async function getFilterOptions(): Promise<FilterOptions> {
  "use cache";
  cacheLife("hours");
  const db = requireDb();

  const [[meta], industries, types, regions, cities, websites, techs] = await Promise.all([
    db.query(`SELECT (SELECT count(*)::int FROM businesses) AS total,
               (SELECT overture_release FROM dataset) AS release,
               (SELECT count(*)::int FROM businesses WHERE industry IS NULL) AS uncategorized,
               EXISTS (SELECT 1 FROM businesses WHERE has_technical_weaknesses) AS weak,
               EXISTS (SELECT 1 FROM businesses WHERE has_low_seo) AS lowseo,
               EXISTS (SELECT 1 FROM businesses WHERE eshop) AS eshop`),
    db.query(`SELECT slug, name_el FROM industries`),
    db.query(`SELECT slug, name_el, industry FROM business_types`),
    db.query(`SELECT DISTINCT unnest(administrative_areas) AS region FROM businesses`),
    db.query(`SELECT region, city FROM (
          SELECT administrative_areas[1] AS region, localities[1] AS city, count(*) AS n
          FROM businesses
          WHERE cardinality(administrative_areas) = 1 AND cardinality(localities) >= 1
          GROUP BY 1, 2
        ) c
        WHERE n >= $1`, [MIN_CITY_BUSINESSES]),
    db.query(`SELECT DISTINCT website_status FROM businesses`),
    db.query(`SELECT DISTINCT unnest(technologies) AS tech FROM businesses`),
  ]);

  const byName = (a: { label: string }, b: { label: string }) => a.label.localeCompare(b.label, "el");

  const industryOptions = industries
    .map((i) => ({
      value: i.slug as string,
      label: i.name_el as string,
      types: types
        .filter((t) => t.industry === i.slug)
        .map((t) => ({ value: t.slug as string, label: t.name_el as string }))
        .sort(byName),
    }))
    .sort(byName);
  if (meta.uncategorized > 0) {
    industryOptions.push({ value: UNCATEGORIZED, label: "Χωρίς σαφή κατηγορία", types: [] });
  }

  const regionOptions = regions
    .map((r) => ({
      value: r.region as string,
      label: r.region as string,
      cities: cities
        .filter((c) => c.region === r.region)
        .map((c) => ({ value: cityValue(c.region, c.city), label: c.city as string }))
        .sort(byName),
    }))
    .sort(byName);

  return {
    total: meta.total,
    release: meta.release,
    industries: industryOptions,
    regions: regionOptions,
    available: {
      website: websites.map((w) => w.website_status as string),
      quality: [...(meta.weak ? ["weak"] : []), ...(meta.lowseo ? ["lowseo"] : [])],
      tech: techs.map((t) => t.tech as string),
      eshop: meta.eshop,
    },
  };
}
