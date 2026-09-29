# Literature & Existing-Tool Gap Analysis

## What already exists

| Pillar | Existing tools / research |
|---|---|
| Infrastructure misconfiguration | OnionScan, onion-nmap; certificate/favicon clearnet pivoting (Cisco Talos); academic Tor hidden-service vulnerability taxonomies |
| Identity graph (handles/PGP/wallets) | PGP-key correlation studies (Wall Street Market), VendorLink (NLP authorship linkage across markets), Maltego-style graphing |
| Stylometry / persona linkage | VeriDark benchmark, multiple 2019–2025 papers on cross-market authorship attribution |
| Collection & commercial platforms | Searchlight, DarkOwl, Flashpoint, Recorded Future, CACI DarkBlue/CluesAI |

## The actual gaps (our contribution)

1. **No unified, fused pipeline.** Every tool above solves one pillar. None
   combine infrastructure + identity-graph + stylometry into a single pipeline
   with one calibrated, shared confidence score flowing between stages.
2. **Individually weak signals, not combined intelligently.** PGP-key matching
   alone is unreliable (Sybil attacks, vendors using multiple keys
   deliberately). Our fusion layer treats each signal as partial evidence,
   weighted together — not a single point of failure.
3. **Black-box or expensive commercial tools.** No open, auditable,
   explainable platform exists at the student/research tier with confidence
   visualization and clean export.
4. **Persona linkage degrades under real adversarial conditions**
   (compartmentalization, short posts, deliberate rebranding). Out of scope
   to fully solve this semester — flagged honestly as a known limitation.

## Our positioning statement
"Existing tools solve infrastructure leaks, identity linking, or stylometry in
isolation, using single unreliable signals. We propose a multi-signal,
confidence-scored attribution framework — combining all three — built and
validated on established, legal research datasets (VeriDark and published DNM
correlation data), with an explainable, investigator-facing confidence layer."
