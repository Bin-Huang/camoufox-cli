/**
 * Browser installation with resilient GitHub release discovery.
 *
 * Anonymous GitHub API requests are limited to 60/hour per IP, which makes
 * installs flaky on servers behind shared egress IPs (CI runners, cloud
 * hosts). Mitigations:
 *
 * - If the API fails, release assets are discovered by paging through
 *   github.com release pages, which are not behind the API rate limit.
 * - The GeoIP database is downloaded from a fixed releases/latest/download
 *   URL (no API involved) at install time and before geoip launches, so
 *   upstream's lazy API-based download never triggers.
 */

import { existsSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { DefaultAddons, maybeDownloadAddons } from "camoufox-js/dist/addons.js";
import { downloadMMDB } from "camoufox-js/dist/locale.js";
import { CamoufoxFetcher, INSTALL_DIR, installedVerStr, launchPath, webdl } from "camoufox-js/dist/pkgman.js";

const HEADERS = { "User-Agent": "camoufox-cli" };
const MMDB_URL = "https://github.com/P3TERX/GeoLite.mmdb/releases/latest/download/GeoLite2-City.mmdb";

async function assetsViaApi(repo: string): Promise<any[]> {
  const resp = await fetch(`https://api.github.com/repos/${repo}/releases`, { headers: HEADERS });
  if (!resp.ok) throw new Error(`GitHub API responded with ${resp.status}`);
  const releases = (await resp.json()) as any[];
  // Skip prereleases/drafts like upstream's fetcher does: their assets can
  // be experimental or incomplete uploads (e.g. missing the browser binary)
  // and must never win over the newest stable release.
  return releases
    .filter((release) => !release.prerelease && !release.draft)
    .flatMap((release) => release.assets ?? []);
}

/**
 * Extract release tags from a listing page, skipping prereleases.
 *
 * The scrape path cannot see the API's `prerelease` flag; on the listing
 * page a prerelease shows a "Pre-release" badge inside its section, i.e.
 * between its tag link and the next release's tag link. Scan tag links and
 * badges as one ordered stream and drop any tag followed by a badge.
 */
export function stableTags(listingHtml: string, repo: string): string[] {
  const escaped = repo.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const tokenRe = new RegExp(`/${escaped}/releases/tag/([^"<]+)|(Pre-release)`, "g");
  const tags: string[] = [];
  const prerelease = new Set<string>();
  let current: string | null = null;
  for (const m of listingHtml.matchAll(tokenRe)) {
    if (m[1] !== undefined) {
      current = m[1];
      if (!tags.includes(current)) tags.push(current);
    } else if (current !== null) {
      prerelease.add(current);
    }
  }
  return tags.filter((t) => !prerelease.has(t));
}

/**
 * Discover release assets by paging through github.com release pages,
 * newest stable release first. Lazy: stops requesting once the caller stops.
 */
export async function* assetsViaWeb(repo: string): AsyncGenerator<any> {
  const escaped = repo.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const tagRe = new RegExp(`/${escaped}/releases/tag/([^"<]+)`, "g");
  const linkRe = new RegExp(`href="(/${escaped}/releases/download/[^"]+)"`, "g");

  const seen = new Set<string>();
  for (let pageNum = 1; ; pageNum++) {
    const listing = await fetch(`https://github.com/${repo}/releases?page=${pageNum}`, { headers: HEADERS });
    if (!listing.ok) throw new Error(`github.com responded with ${listing.status}`);
    const text = await listing.text();
    // Pagination must advance on ANY new tag (a page holding only
    // prereleases is not the end of the listing), while assets are
    // fetched only for the stable ones.
    const pageTags = [...new Set([...text.matchAll(tagRe)].map((m) => m[1]))]
      .filter((tag) => !seen.has(tag));
    if (pageTags.length === 0) return;
    for (const tag of pageTags) seen.add(tag);
    const stable = new Set(stableTags(text, repo));
    for (const tag of pageTags) {
      if (!stable.has(tag)) continue;
      const page = await fetch(`https://github.com/${repo}/releases/expanded_assets/${tag}`, { headers: HEADERS });
      if (!page.ok) continue;
      for (const m of (await page.text()).matchAll(linkRe)) {
        yield {
          name: decodeURIComponent(m[1].split("/").pop()!),
          browser_download_url: `https://github.com${m[1]}`,
        };
      }
    }
  }
}

/** Yield all release assets of a repo, newest release first. */
export async function* iterReleaseAssets(repo: string): AsyncGenerator<any> {
  let assets: any[];
  try {
    assets = await assetsViaApi(repo);
  } catch (e) {
    process.stderr.write(`[camoufox-cli] GitHub API failed (${e}), falling back to github.com pages...\n`);
    yield* assetsViaWeb(repo);
    return;
  }
  yield* assets;
}

class ResilientFetcher extends CamoufoxFetcher {
  async getAsset(): Promise<any> {
    for await (const asset of iterReleaseAssets(this.githubRepo)) {
      const data = this.checkAsset(asset);
      if (data) return data;
    }
    this.missingAssetError();
  }
}

/**
 * Download the GeoIP database if missing, without hitting the GitHub API.
 * Failures are non-fatal: upstream still lazily downloads on first use.
 */
export async function ensureMmdb(): Promise<void> {
  const mmdbFile = join(INSTALL_DIR.toString(), "GeoLite2-City.mmdb");
  if (existsSync(mmdbFile)) return;
  try {
    const buf = await webdl(MMDB_URL, "Downloading GeoIP database", true);
    writeFileSync(mmdbFile, buf);
    return;
  } catch {
    rmSync(mmdbFile, { force: true });
  }
  try {
    await downloadMMDB(); // upstream API-based path, as a last resort
  } catch (e) {
    rmSync(mmdbFile, { force: true });
    process.stderr.write(`[camoufox-cli] GeoIP database download failed (${e}).\n`);
  }
}

/** True when the browser's launch executable is actually on disk. */
function browserPresent(): boolean {
  try {
    launchPath();
    return true;
  } catch {
    return false;
  }
}

/** Download and install the Camoufox browser, GeoIP database and addons. */
export async function installBrowser(): Promise<void> {
  const fetcher = new ResilientFetcher();
  await fetcher.init();

  let installed: string | null = null;
  try {
    installed = installedVerStr();
  } catch {
    installed = null;
  }
  // "Up to date" must mean the browser actually works, not just that
  // version.json matches — otherwise a broken install (version file written
  // but no browser binary) would be masked forever.
  if (installed === fetcher.verstr && browserPresent()) {
    process.stderr.write(`[camoufox-cli] Camoufox v${installed} is already up to date.\n`);
  } else {
    await fetcher.install();
    // A broken release asset (e.g. one missing the browser binary) would
    // otherwise "install" successfully. Fail loudly here instead of at the
    // first `open`.
    launchPath(); // throws CamoufoxNotInstalled if the executable is absent
  }

  await ensureMmdb();
  // Must await: otherwise `install` can return (or crash on --with-deps)
  // while the UBO extract is still in flight, leaving an empty addons/UBO
  // dir that later open() rejects as "manifest.json is missing".
  await maybeDownloadAddons(DefaultAddons);
}
