import { neon } from "@neondatabase/serverless";

// Το DATABASE_URL το βάζει το Vercel όταν η βάση Neon συνδεθεί με το project.
// Τοπικά: `vercel env pull web/.env.local`.
export function getSql() {
  const url = process.env.DATABASE_URL;
  if (!url) return null;
  return neon(url);
}
