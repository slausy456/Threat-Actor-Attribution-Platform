# Ethics & Data Sourcing

## Rule for this repo
**No code in this repository may actively scan, crawl, or connect to live Tor
hidden services or real dark web marketplaces.** All development and the class
demo run entirely on published, legal research datasets.

## Approved data sources
- **VeriDark** — large-scale authorship-verification benchmark built from dark-web
  forum/market text, used for the stylometry module.
- **Published DNM correlation datasets** referenced in academic PGP/identity-graph
  research (e.g., Wall Street Market PGP-key studies, VendorLink's released data)
  — used for the identity-graph module.
- **Synthetic/sample infrastructure-misconfiguration records** — hand-constructed
  examples modeled on documented public case studies (e.g., published Cisco Talos
  writeups) — used for the infrastructure-scan module, since we do not run live
  scans.

## Why this matters
Active reconnaissance against real onion services (even passive-looking checks
like requesting a status page) is a form of unauthorized access to systems we do
not own or have permission to test. Government bodies operating this kind of
system (e.g., NTRO) do so under legal authority a student project does not have.
Building and demoing against legal, published datasets keeps every claim in this
project defensible.

## Path to real-world deployment
Any future phase that involves live data collection from real dark web
infrastructure requires:
1. Institutional legal review and authorization
2. A documented data-minimization and retention policy (see the "safeguards"
   pattern from the related email-forensics project — COLLECT / PRESERVE /
   CONTROL / DISCLOSE)
3. Sign-off from a supervising faculty member or institutional ethics body

This is out of scope for the semester prototype and is tracked as future work
in `roadmap.md`.
