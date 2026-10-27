import { Suspense } from "react";
import { connection } from "next/server";
import { getSql } from "@/lib/db";

type IndustryRow = { slug: string; name_el: string; count: number };

async function Overview() {
  await connection();
  const sql = getSql();
  if (!sql) {
    return <p className="text-zinc-600">Δεν έχει οριστεί DATABASE_URL.</p>;
  }

  const [[totals], industries] = await Promise.all([
    sql`SELECT (SELECT count(*)::int FROM businesses) AS total,
               (SELECT overture_release FROM dataset) AS release`,
    sql`SELECT i.slug, i.name_el, count(b.id)::int AS count
        FROM industries i
        LEFT JOIN businesses b ON b.industry = i.slug
        GROUP BY i.slug, i.name_el
        ORDER BY count DESC`,
  ]);

  return (
    <div className="flex flex-col gap-8">
      <p className="text-lg">
        <strong>{totals.total.toLocaleString("el-GR")}</strong> επιχειρήσεις
        <span className="text-zinc-500"> · Overture {totals.release}</span>
      </p>
      <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {(industries as IndustryRow[]).map((row) => (
          <li
            key={row.slug}
            className="flex justify-between rounded-lg border border-zinc-200 bg-white px-4 py-3"
          >
            <span>{row.name_el}</span>
            <span className="text-zinc-500">{row.count.toLocaleString("el-GR")}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function Home() {
  return (
    <main className="mx-auto w-full max-w-5xl px-4 py-12">
      <h1 className="mb-2 text-3xl font-semibold tracking-tight">Find My Lead</h1>
      <p className="mb-8 text-zinc-600">Ελληνικές επιχειρήσεις ανά κλάδο, περιοχή και στοιχεία επικοινωνίας.</p>
      <Suspense fallback={<p className="text-zinc-500">Φόρτωση…</p>}>
        <Overview />
      </Suspense>
    </main>
  );
}
