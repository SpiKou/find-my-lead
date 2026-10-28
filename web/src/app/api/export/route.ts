import type { NextRequest } from "next/server";
import { EXPORT_COLUMNS, exportBusinesses } from "@/lib/catalog";
import { parseFilters } from "@/lib/filters";

export const maxDuration = 300;

function csvValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  const text = Array.isArray(value) ? value.join("; ") : String(value);
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

// Εξαγωγή CSV με τις στήλες του LeadCatalog και τον λόγο ανενεργού website. Γράφεται σταδιακά (stream),
// ώστε να δουλεύει και για όλο τον κατάλογο.
export async function GET(request: NextRequest) {
  const filters = parseFilters(request.nextUrl.searchParams);
  const encoder = new TextEncoder();

  const stream = new ReadableStream({
    async start(controller) {
      // Το BOM βοηθά το Excel να διαβάσει σωστά τα ελληνικά.
      controller.enqueue(encoder.encode("﻿" + EXPORT_COLUMNS.join(",") + "\n"));
      try {
        for await (const rows of exportBusinesses(filters)) {
          const lines = rows.map((row) => EXPORT_COLUMNS.map((c) => csvValue(row[c])).join(",") + "\n");
          controller.enqueue(encoder.encode(lines.join("")));
        }
        controller.close();
      } catch (error) {
        controller.error(error);
      }
    },
  });

  const date = new Date().toISOString().slice(0, 10);
  return new Response(stream, {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="find-my-lead-${date}.csv"`,
    },
  });
}
