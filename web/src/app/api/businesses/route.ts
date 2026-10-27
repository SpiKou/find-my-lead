import type { NextRequest } from "next/server";
import { searchBusinesses } from "@/lib/catalog";
import { parseFilters } from "@/lib/filters";

// Επόμενη σελίδα αποτελεσμάτων για το «Φόρτωση περισσότερων».
export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const offset = Number(params.get("offset") ?? 0) || 0;
  const { rows } = await searchBusinesses(parseFilters(params), offset);
  return Response.json({ rows });
}
