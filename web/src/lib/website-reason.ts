// Ο λόγος που ένα website βγήκε ανενεργό, όπως τον γράφει το crawl
// (pipeline/crawl_sites.py), σε απλά ελληνικά.
const REASON_LABEL: Record<string, string> = {
  dns: "Το domain δεν υπάρχει",
  timeout: "Δεν απαντά",
  connection: "Αποτυχία σύνδεσης",
  ssl: "Σφάλμα πιστοποιητικού SSL",
  redirects: "Ατέρμονες ανακατευθύνσεις",
  redirect_platform: "Οδηγεί σε άλλη πλατφόρμα (π.χ. Facebook)",
  placeholder: "Προς πώληση ή κενή σελίδα",
};

export function websiteIssue(status: string | null, reason: string | null): string | null {
  if (status !== "inactive" || !reason) return null;
  const http = reason.match(/^http_(\d+)$/);
  if (http) {
    const code = Number(http[1]);
    if (code === 404 || code === 410) return `Η σελίδα δεν βρέθηκε (${code})`;
    if (code >= 500) return `Σφάλμα server (${code})`;
    return `Σφάλμα σελίδας (${code})`;
  }
  return REASON_LABEL[reason] ?? reason;
}
