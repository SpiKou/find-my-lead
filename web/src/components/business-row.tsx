import type { BusinessRow } from "@/lib/catalog";
import { websiteIssue } from "@/lib/website-reason";

const PLATFORMS: Record<string, { label: string; hosts: string[] }> = {
  facebook: { label: "Facebook", hosts: ["facebook.com", "fb.com"] },
  instagram: { label: "Instagram", hosts: ["instagram.com"] },
  linkedin: { label: "LinkedIn", hosts: ["linkedin.com"] },
  youtube: { label: "YouTube", hosts: ["youtube.com", "youtu.be"] },
  tiktok: { label: "TikTok", hosts: ["tiktok.com"] },
  x: { label: "X", hosts: ["x.com", "twitter.com"] },
  pinterest: { label: "Pinterest", hosts: ["pinterest.com", "pinterest.gr"] },
};

const STATUS_DOT: Record<string, string> = {
  active: "bg-emerald-600",
  inactive: "bg-red-500",
  unknown: "bg-zinc-400",
};

const STATUS_LABEL: Record<string, string> = {
  active: "Ενεργό website",
  inactive: "Ανενεργό website",
  unknown: "Μη ελεγμένο website",
};

function domain(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function socialUrl(platform: string, socials: string[]) {
  const hosts = PLATFORMS[platform]?.hosts ?? [];
  return socials.find((url) => hosts.some((host) => domain(url).endsWith(host)));
}

function ContactChip({ href, title, children }: { href?: string; title?: string; children: React.ReactNode }) {
  const className =
    "inline-flex h-7 items-center gap-1.5 rounded-md border border-line bg-canvas/60 px-2 text-xs font-medium text-ink-soft hover:border-ink-soft";
  return href ? (
    <a href={href} title={title} target={href.startsWith("http") ? "_blank" : undefined} rel="noreferrer" className={className}>
      {children}
    </a>
  ) : (
    <span className={className}>{children}</span>
  );
}

export function BusinessRowCard({ row }: { row: BusinessRow }) {
  const others = row.locations_count - 1;
  const issue = websiteIssue(row.website_status, row.website_reason);
  return (
    <li className="grid gap-x-6 gap-y-3 rounded-xl border border-line bg-paper px-4 py-4 md:grid-cols-[1.3fr_1fr_0.9fr_1.2fr] md:items-start">
      <div className="flex min-w-0 gap-3">
        <span className="grid size-9 shrink-0 place-items-center rounded-md bg-canvas text-sm font-semibold text-ink-soft">
          {(row.name.match(/[\p{L}\p{N}]/u)?.[0] ?? "·").toUpperCase()}
        </span>
        <div className="min-w-0">
          <p className="flex items-baseline gap-1 font-semibold">
            {row.website ? (
              <a href={row.website} target="_blank" rel="noreferrer" className="truncate hover:underline">
                {row.name} <span className="text-muted">↗</span>
              </a>
            ) : (
              <span className="truncate">{row.name}</span>
            )}
          </p>
          <p className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted">
            {row.website ? (
              <span className="flex min-w-0 items-center gap-1.5" title={STATUS_LABEL[row.website_status]}>
                <span className={`size-1.5 shrink-0 rounded-full ${STATUS_DOT[row.website_status] ?? "bg-zinc-400"}`} />
                <span className="truncate">{domain(row.website)}</span>
              </span>
            ) : (
              <span>Χωρίς website</span>
            )}
            {issue && <span className="text-red-600">{issue}</span>}
            {row.eshop && (
              <span className="rounded bg-brand-soft px-1.5 py-0.5 font-medium text-brand">E-shop</span>
            )}
          </p>
        </div>
      </div>

      <div className="text-sm">
        <p className="font-medium">{row.business_type_name}</p>
        {row.industry_name && <p className="text-xs text-muted">{row.industry_name}</p>}
      </div>

      <div className="text-sm text-ink-soft">
        <p>{[row.city, row.region].filter(Boolean).join(", ")}</p>
        {others > 0 && (
          <p className="text-xs text-muted">
            +{others} {others === 1 ? "περιοχή" : "περιοχές"}
          </p>
        )}
      </div>

      <div className="flex flex-wrap gap-1.5">
        {row.emails.length > 0 && (
          <ContactChip href={`mailto:${row.emails[0]}`} title={row.emails.join(", ")}>
            Email
          </ContactChip>
        )}
        {row.phones.length > 0 && (
          <ContactChip href={`tel:${row.phones[0]}`} title={row.phones.join(", ")}>
            Τηλέφωνο
          </ContactChip>
        )}
        {row.social_platforms.map((platform) => (
          <ContactChip key={platform} href={socialUrl(platform, row.socials)}>
            {PLATFORMS[platform]?.label ?? platform}
          </ContactChip>
        ))}
      </div>
    </li>
  );
}
