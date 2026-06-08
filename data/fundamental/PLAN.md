# Fundamental Analysis Pipeline — `data/fundamental/`

## Context

Build an offline multi-company fundamental analysis pipeline in `data/fundamental/`. Each company has its own IR website and report format; the pipeline downloads press-release PDFs (or converts HTML to PDF), parses financial tables, normalises metric names across companies, calculates standard indicators, and writes one CSV per company. The AMD v1 scripts in `data/amd_v1/` serve as reference only — all new code is written fresh using shared base classes.

**Companies (Phase 1):** AMD, NVDA, MSFT, Google (GOOG), Circle (CRCL)

**Scope:** Last 10 years only — quarters from 2016-Q2 onwards (today = 2026-05-30). Exception: Circle launched USDC in 2018 and IPO'd in 2025, so collect all available quarters.

---

## Folder Structure

```
data/fundamental/
├── __init__.py
├── base/
│   ├── downloader.py          # BaseDownloader
│   ├── parser.py              # BasePressReleaseParser, BaseFinancialTablesParser
│   ├── metrics_builder.py     # BaseMetricsBuilder
│   └── number_parser.py       # parse_number(), parse_percent()
├── normalizer/
│   ├── canonical_metrics.yaml # synonym map + unit flags per metric
│   └── name_normalizer.py     # NameNormalizer class
├── indicators/
│   └── calculator.py          # FundamentalIndicatorCalculator
├── companies/
│   ├── amd/    {downloader, parser, metrics_builder}.py
│   ├── nvda/   {downloader, parser, metrics_builder}.py
│   ├── msft/   {downloader, parser, metrics_builder}.py
│   ├── goog/   {downloader, parser, metrics_builder}.py
│   └── circle/ {downloader, parser, metrics_builder}.py
├── pipeline.py                # CLI orchestrator
├── reports/                   # Downloaded PDFs per company
│   └── <ticker>/<YYYY-QN>/press_release.pdf [+ financial_tables.pdf]
└── output/
    └── <ticker>_fundamentals.csv
```

---

## GAAP vs Non-GAAP Differentiation

Press releases for all five companies include both GAAP and Non-GAAP financial tables. Both must be extracted and stored with explicit column prefixes.

**Column prefix rules:**
- `gaap_` — GAAP income statement, balance sheet, cash flow line items
- `non_gaap_` — Non-GAAP adjusted figures (exclude SBC, amortization of acquisition intangibles, restructuring, etc.)
- `seg_` — Segment revenue/operating income (always GAAP; not adjusted)
- `ind_` — Calculated indicators; where both GAAP and Non-GAAP versions exist, compute both (e.g. `ind_gross_margin` and `ind_non_gaap_gross_margin`)

**What each prefix captures:**

| Prefix | Typical line items |
|---|---|
| `gaap_` | revenue, gross_profit, gross_margin_pct, r&d_expense, sga_expense, operating_income, operating_margin_pct, interest_expense, net_income, diluted_eps, total_assets, stockholders_equity, total_current_assets/liabilities, long_term_debt, inventories, operating_cash_flow, capital_expenditure |
| `non_gaap_` | gross_profit, gross_margin_pct, operating_expenses, operating_income, operating_margin_pct, net_income, diluted_eps (adjusted for SBC, acquisition amortization; specific line items vary per company) |
| `seg_` | per-company segment breakdown (see table below) |

**Key Non-GAAP adjustments (per company):**
- **AMD/NVDA:** SBC, amortization of acquired intangible assets, acquisition-related costs, inventory write-downs
- **MSFT:** SBC, acquisition-related amortization (especially post-Activision); also reports GAAP-only for cloud segment margins
- **GOOG:** SBC only (primary adjustment); reports both GAAP and Non-GAAP operating income per segment since 2024
- **Circle:** Adjusted EBITDA (adds back SBC + D&A); limited Non-GAAP disclosure given recent IPO

**Parser responsibility:** `BasePressReleaseParser.parse()` returns `{"gaap": DataFrame, "non_gaap": DataFrame}`. The metrics builder's `extract_raw_metrics()` reads from the `gaap` DataFrame for `gaap_*` keys and from the `non_gaap` DataFrame for `non_gaap_*` keys. Segment data comes from the financial tables parser's `"segment_data"` section.

---

## Company-Specific Growth Metrics

Each company's `extract_raw_metrics()` extracts these company-specific segment/growth metrics in addition to the standard GAAP/Non-GAAP income statement items. These use the `seg_` prefix.

### AMD — Key growth driver: AI/Data Center transition
| Column | Source label in press release |
|---|---|
| `seg_datacenter_revenue` | "Data Center" segment revenue |
| `seg_datacenter_operating_income` | "Data Center" segment operating income |
| `seg_client_revenue` | "Client" segment revenue (PC CPUs) |
| `seg_client_operating_income` | "Client" segment operating income |
| `seg_gaming_revenue` | "Gaming" segment revenue (discrete GPUs, semi-custom) |
| `seg_gaming_operating_income` | "Gaming" segment operating income |
| `seg_embedded_revenue` | "Embedded" segment revenue (FPGA/Xilinx) |
| `seg_embedded_operating_income` | "Embedded" segment operating income |
| `non_gaap_adjusted_ebitda` | Non-GAAP Adjusted EBITDA (reconciliation table) |

### NVIDIA — Key growth driver: Data Center AI accelerators
| Column | Source label |
|---|---|
| `seg_data_center_revenue` | "Data Center" revenue (H100/H200/B200 GPUs, NVLink, networking) |
| `seg_data_center_operating_income` | "Data Center" operating income |
| `seg_gaming_revenue` | "Gaming" revenue (GeForce consumer GPUs) |
| `seg_professional_visualization_revenue` | "Professional Visualization" revenue (RTX workstation) |
| `seg_automotive_revenue` | "Automotive" revenue (DRIVE platform) |
| `seg_oem_other_revenue` | "OEM & Other" revenue |
| `non_gaap_gross_margin_pct` | Non-GAAP gross margin % |
| `non_gaap_operating_margin_pct` | Non-GAAP operating margin % |

### Microsoft — Key growth driver: Azure cloud + Microsoft 365
| Column | Source label |
|---|---|
| `seg_intelligent_cloud_revenue` | "Intelligent Cloud" segment revenue (Azure, SQL Server, Windows Server) |
| `seg_intelligent_cloud_operating_income` | "Intelligent Cloud" operating income |
| `seg_productivity_biz_revenue` | "Productivity and Business Processes" revenue (M365, LinkedIn, Dynamics) |
| `seg_productivity_biz_operating_income` | "Productivity and Business Processes" operating income |
| `seg_more_personal_computing_revenue` | "More Personal Computing" revenue (Windows OEM, Xbox, Search) |
| `seg_more_personal_computing_operating_income` | "More Personal Computing" operating income |
| `seg_azure_growth_pct` | Azure and other cloud services revenue growth % YoY (MSFT only reports %, not absolute) |
| `seg_m365_commercial_revenue` | Microsoft 365 Commercial products & cloud services revenue |
| `non_gaap_operating_income` | Non-GAAP operating income (excludes SBC, acquisition amortization) |
| `non_gaap_diluted_eps` | Non-GAAP diluted EPS |

### Google/Alphabet — Key growth driver: Search + Cloud
| Column | Source label |
|---|---|
| `seg_google_search_revenue` | "Google Search & other" advertising revenue |
| `seg_youtube_ads_revenue` | "YouTube ads" revenue |
| `seg_google_network_revenue` | "Google Network" revenue (AdSense, AdMob) |
| `seg_google_subscriptions_revenue` | "Google subscriptions, platforms & devices" (Play Store, Pixel, YouTube Premium) |
| `seg_google_services_total_revenue` | "Google Services" total revenue |
| `seg_google_services_operating_income` | "Google Services" operating income |
| `seg_google_cloud_revenue` | "Google Cloud" revenue (GCP + Google Workspace) |
| `seg_google_cloud_operating_income` | "Google Cloud" operating income |
| `seg_other_bets_revenue` | "Other Bets" revenue (Waymo, Verily, etc.) |
| `non_gaap_operating_income` | Non-GAAP operating income (primarily SBC add-back) |
| `non_gaap_net_income` | Non-GAAP net income |
| `non_gaap_diluted_eps` | Non-GAAP diluted EPS |

### Circle — Key growth driver: USDC circulation + reserve yield
| Column | Source label |
|---|---|
| `seg_usdc_reserve_income` | Net interest income from USDC reserves (primary revenue) |
| `seg_subscription_services_revenue` | SaaS / Circle Mint / institutional services revenue |
| `seg_usdc_circulation` | USDC total supply in circulation (billions; key KPI, not a revenue line) |
| `seg_reserve_yield_pct` | Effective yield on USDC reserves (%) |
| `non_gaap_adjusted_ebitda` | Adjusted EBITDA (GAAP net income + SBC + D&A + taxes) |

> **Note on `seg_azure_growth_pct` and `seg_usdc_circulation`:** These are disclosed differently from dollar revenues. Azure growth is reported only as a YoY percentage. USDC circulation is a balance/KPI metric. Both are captured as-is since they are key indicators of business momentum.

---

## Fundamental Indicators to Calculate

All stored with `ind_` prefix, as floats 0–1 for ratios, dollar amounts for `ind_net_debt`.

| Indicator | Formula |
|---|---|
| `ind_gross_margin` | gaap_gross_profit / gaap_revenue |
| `ind_non_gaap_gross_margin` | non_gaap_gross_profit / gaap_revenue |
| `ind_operating_margin` | gaap_operating_income / gaap_revenue |
| `ind_non_gaap_operating_margin` | non_gaap_operating_income / gaap_revenue |
| `ind_net_margin` | gaap_net_income / gaap_revenue |
| `ind_roe` | TTM net_income / avg(stockholders_equity) — rolling 4-quarter |
| `ind_roa` | TTM net_income / avg(total_assets) |
| `ind_current_ratio` | total_current_assets / total_current_liabilities |
| `ind_quick_ratio` | (total_current_assets − inventories) / total_current_liabilities |
| `ind_debt_to_equity` | long_term_debt / stockholders_equity |
| `ind_net_debt` | long_term_debt − cash_and_short_term_investments (dollar $M) |
| `ind_interest_coverage` | gaap_operating_income / abs(interest_expense) |
| `ind_ocf_margin` | operating_cash_flow / gaap_revenue |
| `ind_fcf_margin` | free_cash_flow / gaap_revenue |
| `ind_fcf_conversion` | free_cash_flow / gaap_net_income |
| `ind_capex_intensity` | abs(capital_expenditure) / gaap_revenue |
| `ind_revenue_qoq` | (revenue[t] − revenue[t−1]) / abs(revenue[t−1]) |
| `ind_revenue_yoy` | (revenue[t] − revenue[t−4]) / abs(revenue[t−4]) |
| `ind_eps_yoy` | (diluted_eps[t] − diluted_eps[t−4]) / abs(diluted_eps[t−4]) |

---

## Base Layer (`data/fundamental/base/`)

### `number_parser.py`
Ported from `amd_v1/build_quarterly_metrics.py`:
- `parse_number(s)` — "$1,234" → 1234.0, "(567)" → -567.0, "—"/None → None
- `parse_percent(s)` — "44%" → 0.44; plain number returned as-is

### `downloader.py` — `BaseDownloader`
```python
class BaseDownloader(ABC):
    REQUEST_DELAY = 1.0
    MAX_RETRIES = 3
    MIN_QUARTER = "2016-Q2"   # 10-year lookback cutoff; override for newer companies

    # Abstract (each company implements these):
    def list_quarters(self) -> list[dict]:
        # Returns [{label, press_url, tables_url or None}, ...]
        # Base run() filters out quarters with slug < MIN_QUARTER automatically

    def download_quarter(self, quarter: dict, out_dir: Path, force=False): ...

    # Shared (inherited by all companies):
    def fetch(self, url, **kwargs) -> requests.Response   # retry + rate-limit
    def save_pdf(self, content, path)                      # atomic write
    def slug(self, label) -> str                           # "Q3 2024" → "2024-Q3"
    def html_to_pdf(self, html, dest)                      # weasyprint fallback
    def run(self, out_dir, force, latest, quarter)         # CLI driver; skips slug < MIN_QUARTER
```

### `parser.py` — two abstract base parsers

**`BasePressReleaseParser`**
- Shared helpers from `amd_v1/press_release_parser.py`: `normalize_header()`, `similarity()`, `table_to_df()`
- Abstract `parse(pdf_path) -> dict[str, DataFrame]` returning at minimum `"gaap"` and `"non_gaap"` keys
- Subclasses set `GAAP_HEADER` / `NON_GAAP_HEADER` class vars to match company-specific wording

**`BaseFinancialTablesParser`**
- Contains the full PyMuPDF word-position grid reconstruction from `amd_v1/financial_tables_parser.py` as protected `_` methods: `_group_into_rows()`, `_cluster_xs()`, `_is_date_token()`, `_parse_section()`, `_parse_page()`
- `PAGE_SECTION_KEYS` class var maps section names to keyword lists (defaults = AMD keywords)
- `_detect_sections(page_text, found_sections) -> str|None` — overridable
- Concrete `parse(pdf_path)` calls `_detect_sections()` so subclasses only override keywords, not the 400-line reconstruction algorithm
- Subclasses that have no separate `financial_tables.pdf` (MSFT, GOOG) override `parse()` completely to return empty dict; their parsers read from the press release HTML instead

### `metrics_builder.py` — `BaseMetricsBuilder`
```python
class BaseMetricsBuilder(ABC):
    # Abstract:
    def extract_raw_metrics(self, tables, col, quarter) -> dict[str, str|None]: ...
    # Returns canonical snake_case keys → raw string values ("1,234", "46%")

    # Shared:
    @staticmethod
    def resolve_metric(index, metric, cutoff=0.82, normalizer=None) -> str|None
    # 4-stage: exact → case-insensitive → fuzzy (difflib) → synonym expansion

    @staticmethod
    def get(df, metric, occurrence=0, col=0, normalizer=None) -> str|None

    def build_dataframe(self, reports_dir, normalizer, run_check=True) -> tuple[DataFrame, ValidationReport]
    # Iterates sorted quarter dirs → calls extract_raw_metrics → Layer 1 cross-check →
    # Layer 2 internal consistency → converts raw strings to floats
    # Returns both the data DataFrame and a ValidationReport with all warnings

    def cross_check(self, quarter, prior_in_current, prev_current, keys=None) -> list[ValidationIssue]
    # Layer 1: validates col-1 values against prior quarter's col-0 (±0.5% tolerance)
    # Detects sequential vs YoY column before comparing

    def consistency_check(self, quarter, metrics) -> list[ValidationIssue]
    # Layer 2: checks arithmetic relationships within a single quarter's extracted metrics
```

---

## Name Normalization (`data/fundamental/normalizer/`)

### `canonical_metrics.yaml` schema
```yaml
metrics:
  - canonical: gaap_revenue
    label: "Revenue"
    unit: amount        # amount | ratio | count
    is_percentage: false
    section: income_statement
    synonyms:
      - "Net revenue"
      - "Total net revenues"
      - "Revenue"
    company_aliases:
      msft: "Revenue"
      goog: "Revenues"

  - canonical: gaap_gross_profit
    label: "Gross Profit"
    unit: amount
    is_percentage: false
    section: income_statement
    synonyms:
      - "Gross profit"
      - "Gross income"        # INTC historical alias
      - "Gross margin"        # when value is dollar amount (no % in cell)

  - canonical: gaap_gross_margin_pct
    label: "Gross Margin %"
    unit: ratio
    is_percentage: true        # raw "44%" → stored as 0.44
    section: income_statement
    synonyms:
      - "Gross margin %"
      - "Gross profit margin"
      - "Gross margin"         # when parser appends " %" to label
  # ... ~35 metrics total covering income stmt, balance sheet, cash flow,
  # per-share, and segment revenue fields
```

**Unit disambiguation ("margin" problem):** The parser appends ` %` to any label whose row contains `%` values. So "Gross margin" with dollar values stays `"Gross margin"` → maps to `gaap_gross_profit`; "Gross margin" with `%` values becomes `"Gross margin %"` → maps to `gaap_gross_margin_pct`. Ambiguity resolved at parse time.

### `name_normalizer.py` — `NameNormalizer`
- Loads YAML, builds two dicts: `canonical → metadata` and `synonym.lower() → canonical`
- `to_canonical(raw_label)` — direct lookup; `None` if not found (caller falls back to fuzzy)
- `get_synonyms(label)` — returns all synonyms for a canonical or synonym key
- `is_percentage(canonical)` — whether to call `parse_percent()` vs `parse_number()`

---

## Validation Strategy

Parsers can extract wrong numbers due to column misalignment, OCR artifacts, table layout changes, or wrong section detection. A multi-layer validation catches these before they pollute the CSV.

### Layer 1 — Cross-report continuity check (primary guard)

Every quarterly press release reports the *current* quarter (col 0) **and** the *prior* quarter (col 1) for comparison. This means the same number appears in two consecutive reports: once as col 0 in report Q, and once as col 1 in report Q+1.

When building the DataFrame, after extracting each quarter:
```
report[Q].col=1  →  should equal  report[Q-1].col=0
```
If they diverge beyond tolerance, parsing almost certainly went wrong for one of the two quarters.

**Implementation in `BaseMetricsBuilder.cross_check()`:**
- Called after each quarter is processed (already exists in AMD v1, generalised here)
- Compares a fixed set of cross-check keys (configurable per company) between the current report's prior-quarter column and the previously stored current-quarter values
- Tolerances: `±0.5%` for dollar amounts ≥ $10M; `±$0.015` for EPS; `±0.5pp` for margin percentages
- Detects whether col 1 is sequential (Q-1) or year-over-year (Q-4) from column date headers before comparing
- Outcome: `WARN` log per mismatch with both values shown; the quarter is still written but flagged

**Cross-check keys (universal — all companies):**
`gaap_revenue`, `gaap_gross_profit`, `gaap_operating_income`, `gaap_net_income`, `gaap_diluted_eps`, `non_gaap_gross_profit`, `non_gaap_operating_income`, `non_gaap_diluted_eps`

Plus company-specific additions (e.g. AMD adds `seg_datacenter_revenue`; MSFT adds `seg_intelligent_cloud_revenue`).

### Layer 2 — Internal consistency checks (within a single quarter)

After extracting raw metrics for quarter Q, check arithmetic relationships that must hold:

| Check | Formula | Tolerance |
|---|---|---|
| Revenue decomposition | `gaap_revenue ≈ Σ seg_*_revenue` (when all segments reported) | ±1% |
| Gross profit derivation | `gaap_gross_profit ≈ gaap_revenue − gaap_cost_of_revenue` | ±0.5% |
| Operating income derivation | `gaap_operating_income ≈ gaap_gross_profit − gaap_total_opex` | ±1% |
| Non-GAAP ≥ GAAP gross profit | `non_gaap_gross_profit ≥ gaap_gross_profit` (adjustments are additive) | strict |
| Margin consistency | `gaap_gross_margin_pct ≈ gaap_gross_profit / gaap_revenue` | ±0.5pp |
| EPS sign | `sign(gaap_diluted_eps) == sign(gaap_net_income)` | strict |
| Positive revenue | `gaap_revenue > 0` | strict |

Failures are logged as `WARN` with the check name, computed vs reported values, and quarter. They do not block writing.

### Layer 3 — Sanity bounds (outlier detection)

Applied after the full DataFrame is built (all quarters processed):

- Revenue QoQ change > ±80%: flag (possible unit scale error — millions vs billions)
- Gross margin outside 0%–100%: flag (almost certainly a parsing error)
- EPS magnitude differs from prior 4-quarter average by > 10×: flag
- Any value that is exactly 0.0 where prior quarters show non-zero: flag as possible missed parse

These are cheap DataFrame-level checks in `FundamentalIndicatorCalculator.validate(df)` before writing the CSV.

### Validation output

`build_dataframe()` collects all warnings into a `ValidationReport` dataclass:
```python
@dataclass
class ValidationIssue:
    quarter: str
    layer: int          # 1, 2, or 3
    check: str          # e.g. "cross_check:gaap_revenue" or "consistency:gross_profit"
    expected: float | None
    actual: float | None
    pct_diff: float | None

@dataclass  
class ValidationReport:
    issues: list[ValidationIssue]
    def summary(self) -> str: ...     # tabular print of all issues
    def has_errors(self) -> bool: ... # True if any strict check failed
```

The `ValidationReport` is:
1. Printed to stdout after each company run
2. Written to `output/<ticker>_validation.txt` alongside the CSV

**CLI integration:**
```
python -m data.fundamental.pipeline run --company amd        # runs validation, prints warnings
python -m data.fundamental.pipeline validate --company amd   # re-runs validation on existing CSV without re-downloading
```

### What validation does NOT do

- It never auto-corrects extracted values. The CSV always contains what was parsed, never a synthesised fix.
- It does not block CSV output on `WARN`. Only a `strict` failure (e.g. negative revenue) would raise an exception, and even then only if `--strict` flag is passed to the CLI.

---

## Handling Format Changes Across Quarters

Report layouts change over 10 years: sections get renamed, new reconciliation tables are added, segments are split or merged, columns shift. The pipeline must be resilient — a format change in one quarter should never crash the run or silently corrupt other quarters.

### Resilience rules (enforced in `BaseMetricsBuilder.build_dataframe()`)

1. **Never crash on a missing section.** If `financial_tables["segment_data"]` is absent or a required key is not found in a DataFrame, log a warning and store `None` for that metric. Continue to the next quarter.

2. **Never crash on a missing metric.** `BaseMetricsBuilder.get()` always returns `None` (not an exception) when `resolve_metric()` finds no match. The metrics builder logs the unresolved name + quarter for later diagnosis.

3. **Log all unresolved metrics per quarter.** After processing each quarter, print a summary: `2018-Q1: 3 metrics unresolved: [non_gaap_adjusted_ebitda, seg_embedded_revenue, gaap_interest_expense]`. This makes format drift visible without requiring manual inspection of every quarter.

4. **Fuzzy section header matching.** `_detect_sections()` uses `difflib.get_close_matches(page_text_block, known_keywords, cutoff=0.7)` in addition to substring checks. This handles renamings like "Selected Corporate Data" → "Supplemental Data" without code changes.

5. **Per-metric fallback lists in metrics builder.** Each `extract_raw_metrics()` implementation can specify ordered fallback names for a metric that changed label over time. Example for AMD: `gaap_gross_profit` tries `["Gross profit", "Gross margin"]` in order (the label changed between 2017 and 2020). This is declared in `canonical_metrics.yaml` under `synonyms` and automatically tried by `resolve_metric()` via the `NameNormalizer`.

6. **Cross-quarter continuity check is warn-only.** `cross_check()` logs mismatches but never blocks a quarter from being written. A mismatch flags a format issue to investigate, not a fatal error.

7. **Segment structural changes.** When a company redefines segments (e.g. AMD merged its CPU+GPU segments and later split again; NVDA added Automotive as a major segment in 2021), the old segment columns become `None` and new ones populate. This is the expected behaviour — do not synthesise/backfill values across structural changes. The CSV will have gaps, which honestly represent the history.

### Practical examples of known format changes to handle

| Company | Change | Quarters affected | Handling |
|---|---|---|---|
| AMD | Segment names changed: "Computing & Graphics" + "Enterprise, Embedded & Semi-Custom" → current 4-segment model | Pre-2022 | Old segment columns `None`; new segment columns `None` for pre-2022 |
| AMD | `Adjusted EBITDA` reconciliation table added | From ~2022-Q4 | `None` before table existed |
| AMD | `Gross profit` label was `Gross margin` in early press releases | Pre-2020 | Handled via `synonyms` in YAML |
| NVDA | Fiscal calendar: quarter label format changed on IR page | Historically | `slug()` normalises to calendar quarter |
| MSFT | Segment structure changed post-Activision acquisition (2023) | From FY2024-Q1 | Gaming merged into More Personal Computing |
| GOOG | Google Cloud started reporting operating income | From 2021-Q4 | `None` for prior quarters |
| GOOG | YouTube revenue broken out separately | From 2020-Q1 | `None` for prior quarters |

## Per-Company Implementations

### AMD (`companies/amd/`)
- IR URL: `https://ir.amd.com/financial-information/financial-results`
- **Downloader:** BeautifulSoup scrape of IR page → extract quarter boxes → download `press_release.pdf` + `financial_tables.pdf`
- **Parser:** `AmdPressReleaseParser` returns `{"gaap": df, "non_gaap": df}` by fuzzy-matching headers in the press release. `AmdFinancialTablesParser` inherits `BaseFinancialTablesParser` with default `PAGE_SECTION_KEYS`; returns `segment_data`, `balance_sheet`, `cash_flow`, `gaap_to_non_gaap`, `adjusted_ebitda` sections.
- **Metrics builder:** Reads GAAP P&L from `press_release["gaap"]`, Non-GAAP from `press_release["non_gaap"]`, segments from `financial_tables["segment_data"]`. Extracts all columns in the GAAP/Non-GAAP/segment tables defined above.

### NVIDIA (`companies/nvda/`)
- IR URL: `https://investor.nvidia.com/financial-info/financial-reports/default.aspx`
- **Downloader:** Scrapes quarterly results page; NVDA uses fiscal quarters (FQ1 FY2026 = calendar Q1 2026) — `slug()` override maps fiscal quarter end month to calendar quarter label
- **Parser:** `NvdaPressReleaseParser` returns `{"gaap": df, "non_gaap": df}`. `NvdaFinancialTablesParser` overrides `PAGE_SECTION_KEYS` to match NVDA header wording (e.g. "CONDENSED CONSOLIDATED STATEMENTS OF INCOME").
- **Metrics builder:** Same two-source pattern as AMD. Segment data (5 segments) comes from financial tables.

### Microsoft (`companies/msft/`)
- IR URL: `https://www.microsoft.com/en-us/Investor/earnings/` (index page)
- Quarter URL pattern: `/Investor/earnings/FY-YYYY-QN/press-release-webcast` — HTML only
- **Downloader:** Scrapes earnings index → for each quarter, fetches press-release HTML → converts to PDF via `html_to_pdf()` (weasyprint). No separate financial tables file; all data is in the press-release PDF.
- **Parser:** `MsftPressReleaseParser` handles both GAAP and Non-GAAP tables; overrides `PAGE_SECTION_KEYS` for MSFT headings ("INCOME STATEMENTS", "SEGMENT REVENUE AND OPERATING INCOME"). MSFT embeds segment data in the same press-release document.
- **Metrics builder:** MSFT fiscal year ends June 30; quarter slugs map as FY-YYYY-Q1 = Oct–Dec. Extracts `seg_azure_growth_pct` as a special case (% string, not dollar amount).

### Google/Alphabet (`companies/goog/`)
- IR URL: `https://abc.xyz/investor/` (earnings releases listed with PDF links)
- **Downloader:** Scrapes abc.xyz investor page for quarterly PDF links → downloads `press_release.pdf`
- **Parser:** `GoogPressReleaseParser` returns `{"gaap": df, "non_gaap": df}` + segment tables. Google embeds all financials in a single press-release PDF.
- **Metrics builder:** Extracts 6 revenue lines under Google Services plus Google Cloud and Other Bets. `seg_google_cloud_operating_income` captures Google Cloud's profitability trajectory (turned profitable in 2023).

### Circle (`companies/circle/`)
- IR URL: `https://investor.circle.com/financials/quarterly-results/default.aspx`
- **Downloader:** Scrapes quarterly results page → downloads PDF press releases
- **Parser:** `CirclePressReleaseParser` returns `{"gaap": df, "non_gaap": df}`. Circle's primary revenue is interest income on USDC reserves — the GAAP income statement structure differs from semiconductor companies (no "cost of goods sold"; margin structure is more bank-like).
- **Metrics builder:** Extracts `gaap_revenue` (total), `seg_usdc_reserve_income`, `seg_subscription_services_revenue`, `seg_usdc_circulation` (KPI, not a revenue line). `seg_usdc_circulation` is a balance metric reported in billions; stored as-is.
- Note: IPO June 2025 — limited quarters available; `ind_revenue_yoy` will be `NaN` for early quarters.

---

## Pipeline Orchestrator (`pipeline.py`)

```
python -m data.fundamental.pipeline run --company amd
python -m data.fundamental.pipeline run --all
python -m data.fundamental.pipeline download --company nvda --latest
python -m data.fundamental.pipeline parse --company amd --quarter 2024-Q3
```

`Pipeline.run()` sequence:
1. `download()` → `BaseDownloader.run()` → PDFs land in `reports/<ticker>/<YYYY-QN>/`
2. `build()` → `BaseMetricsBuilder.build_dataframe()` → wide DataFrame of raw floats
3. `calculate()` → `FundamentalIndicatorCalculator.calculate(raw_df)` → appends `ind_` columns
4. `write()` → `output/<ticker>_fundamentals.csv`

**Company registry** (in `pipeline.py`): a dict mapping ticker → `{downloader, builder}` dotted class paths. Adding a new company = add one entry + create `companies/<ticker>/` folder.

---

## CSV Output Format

- **Index:** `quarter` column, values `"YYYY-QN"` (e.g. `"2024-Q3"`)
- **Column prefixes:** `gaap_` (GAAP P&L + B/S + cash flow), `non_gaap_` (Non-GAAP adjusted figures), `seg_` (segment revenue/income + company-specific KPIs), `ind_` (calculated indicators)
- **Percentages:** stored as float 0–1 (e.g. 0.44 for 44%); `canonical_metrics.yaml` `is_percentage` flag controls this. Exception: `seg_azure_growth_pct` and `seg_reserve_yield_pct` stored as 0–1 float too.
- **Dollar amounts:** plain float in millions (as reported by the company; billions for `seg_usdc_circulation`)
- **Missing values:** empty cells (pandas NaN → empty string in CSV); no "N/A" strings
- **Column order:** `gaap_` income stmt → `gaap_` balance sheet → `gaap_` cash flow → `seg_` → `non_gaap_` → `ind_`
- **GAAP/Non-GAAP indicator pairs:** where both bases are meaningful, both are calculated: e.g. `ind_gross_margin` (GAAP) and `ind_non_gaap_gross_margin`; `ind_operating_margin` and `ind_non_gaap_operating_margin`; `ind_net_margin` and `ind_non_gaap_net_margin`

---

## Implementation Sequence

1. **Base layer:** `base/number_parser.py`, `base/downloader.py`, `base/parser.py`, `base/metrics_builder.py`
2. **Normalization:** `normalizer/canonical_metrics.yaml` (AMD + NVDA metrics first), `normalizer/name_normalizer.py`
3. **AMD company:** `companies/amd/` — validate output matches `amd_v1/quarterly_metrics.csv` semantically
4. **Indicators:** `indicators/calculator.py` — test with AMD data
5. **Pipeline:** `pipeline.py` — wire together with AMD working end-to-end
6. **NVDA:** `companies/nvda/` — add NVDA-specific synonyms to canonical_metrics.yaml
7. **MSFT, GOOG:** implement with weasyprint HTML-to-PDF path; extend canonical_metrics.yaml
8. **Circle:** implement last (fewest quarters, most distinct metrics)

---

## Dependencies

Add to `requirements.txt`:
```
weasyprint>=60.0   # HTML-to-PDF for MSFT, GOOG if no direct PDF
```
All other dependencies (requests, beautifulsoup4, pymupdf, pyyaml, pandas) already present.

---

## Verification

```bash
pyenv activate claude-stock

# Test AMD end-to-end (uses existing reports in data/amd_v1/reports/ as reference)
python -m data.fundamental.pipeline run --company amd --no-download
# Verify: output/amd_fundamentals.csv has same revenue/EPS/gross profit as amd_v1/quarterly_metrics.csv

# Test download of 1 quarter
python -m data.fundamental.pipeline download --company nvda --latest

# Inspect parsed tables for a quarter
python -m data.fundamental.pipeline parse --company amd --quarter 2024-Q3

# Run all companies (skip download if PDFs already present)
python -m data.fundamental.pipeline run --all --no-download
```
