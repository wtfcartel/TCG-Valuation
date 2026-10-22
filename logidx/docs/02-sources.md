# 02 — Source coverage and status

Status key — **Implemented**: code and offline tests exist. **Live-verified**: confirmed against the real service.
As of 2026-10-22, **no source has been live-verified**: the build environment's network policy blocked every job-site
and API host, and no Adzuna or xAI keys were available. Run `logidx probe` where network access is available, and
record the results here.

| # | Target source | Access route in LogiDx | Implemented | Live-verified | Notes |
|---|---|---|---|---|---|
| 1 | SEEK Australia | None (restricted) | Recorded as NOT SEARCHED | n/a | No candidate search API. Compliant routes: SEEK saved-search alert emails via Gmail (Phase 4); manual import |
| 2 | Google Jobs | None (restricted); optional Google Programmable Search as an *indexed fallback* | Fallback adapter implemented | No | Fallback results are INDEXED FALLBACK ONLY, verified separately, and never count as a native search. Check that the Programmable Search JSON API is still offered to new customers |
| 3 | LinkedIn Jobs | None (restricted) | Recorded as NOT SEARCHED | n/a | Alert emails (Phase 4); manual import |
| 4 | Indeed Australia | None (restricted) | Recorded as NOT SEARCHED | n/a | Publisher API closed to new users |
| 5 | Jora Australia | None (restricted) | Recorded as NOT SEARCHED | n/a | No public API identified |
| 6 | CareerOne | None (restricted) | Recorded as NOT SEARCHED | n/a | Partly reachable through Adzuna's aggregation |
| 7 | Adzuna Australia | Official keyed API | Yes | No | Snippet descriptions; predicted salaries discarded; searches Australia-wide before geographic classification |
| 8 | Workforce Australia | None (restricted) | Recorded as NOT SEARCHED | n/a | No documented public API identified; investigate |
| 9 | EthicalJobs | RSS/Atom adapter | Yes (feed URL blank) | No | Add a feed URL in `watchlist.yaml` if one is published |
| 10 | Pro Bono Australia | RSS/Atom adapter | Yes (feed URL blank) | No | As above |
| 11 | Executive search sites | Bullhorn public career-portal API; RSS | Yes | No | Agencies are listed in the watchlist; identifiers not yet confirmed (Six Degrees appears to use Bullhorn, given the BH- reference) |
| 12 | Employer careers / ATS | Workday CXS, SmartRecruiters, Greenhouse, Lever, PageUp public endpoints | Yes | No | 21 employers listed (including trivago); ATS type and identifiers to be confirmed per employer |

## Enabling an employer board

1. Open the employer's careers site and click into any job.
2. Read the vendor and identifier from the URL (see the header of `config/watchlist.yaml`).
3. Set `ats:` and fill in `board:`, then run `logidx probe`. Only a board that reports `OK` counts as searchable.

## Adding a new adapter

Implement `QuerySource.search` or `BoardSource.fetch` (in `sources/base.py`) and return a `FetchResult`. Set
`truncated=True` whenever the listing may be incomplete. Raise `SourceError(blocked=True)` for access refusals. Then
register the adapter in `sources/registry.py` and add respx tests built on a vendor-shaped payload.
