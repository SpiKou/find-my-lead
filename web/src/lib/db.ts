import { neon } from "@neondatabase/serverless";

export type Row = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export type Db = {
  query: (text: string, params?: unknown[]) => Promise<Row[]>;
};

let db: Db | null = null;

// Στο Vercel μιλάμε με το Neon μέσω HTTP. Για τοπική Postgres (localhost)
// ο HTTP driver δεν δουλεύει, οπότε χρησιμοποιούμε το node-postgres.
export function getDb(): Db | null {
  if (db) return db;
  const url = process.env.DATABASE_URL;
  if (!url) return null;

  const host = new URL(url).hostname;
  if (host === "localhost" || host === "127.0.0.1") {
    const pool = import("pg").then(({ Pool }) => new Pool({ connectionString: url }));
    db = { query: async (text, params = []) => (await (await pool).query(text, params)).rows };
  } else {
    const sql = neon(url);
    db = { query: (text, params = []) => sql.query(text, params) as Promise<Row[]> };
  }
  return db;
}
