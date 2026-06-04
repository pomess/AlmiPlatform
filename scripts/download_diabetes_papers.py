"""
Download ~500 diabetes papers from PubMed via BioMCP CLI.

Prerequisites:
    pip install biomcp-cli

Optional (improves rate limits):
    export NCBI_API_KEY="your-key"
    export S2_API_KEY="your-key"

Usage:
    python scripts/download_diabetes_papers.py
"""

import json
import subprocess
import sys
import time
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent.parent / "data" / "diabetes_papers"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TARGET_COUNT = 500
BATCH_SIZE = 50  # biomcp typically caps around 50 per query

SEARCH_QUERIES = [
    # Broad diabetes queries with different sub-topics to maximize coverage
    {"disease": "type 2 diabetes", "keywords": "pathophysiology"},
    {"disease": "type 2 diabetes", "keywords": "insulin resistance"},
    {"disease": "type 2 diabetes", "keywords": "treatment"},
    {"disease": "type 2 diabetes", "keywords": "metformin"},
    {"disease": "type 2 diabetes", "keywords": "GLP-1"},
    {"disease": "type 2 diabetes", "keywords": "SGLT2 inhibitors"},
    {"disease": "type 1 diabetes", "keywords": "autoimmune"},
    {"disease": "type 1 diabetes", "keywords": "insulin therapy"},
    {"disease": "diabetes mellitus", "keywords": "complications"},
    {"disease": "diabetes mellitus", "keywords": "cardiovascular"},
    {"disease": "diabetes mellitus", "keywords": "nephropathy"},
    {"disease": "diabetes mellitus", "keywords": "retinopathy"},
    {"disease": "diabetes mellitus", "keywords": "neuropathy"},
    {"disease": "diabetic ketoacidosis", "keywords": "management"},
    {"disease": "gestational diabetes", "keywords": "pregnancy"},
    {"disease": "diabetes", "keywords": "biomarkers"},
    {"disease": "diabetes", "keywords": "genetics"},
    {"disease": "diabetes", "keywords": "epidemiology"},
    {"disease": "diabetes", "keywords": "prevention"},
    {"disease": "diabetes", "keywords": "obesity"},
    {"disease": "diabetes", "keywords": "HbA1c"},
    {"disease": "diabetes", "keywords": "beta cell"},
    {"disease": "diabetes", "keywords": "glucagon"},
    {"disease": "diabetes", "keywords": "continuous glucose monitoring"},
    {"disease": "diabetes", "keywords": "artificial pancreas"},
]


def run_biomcp_search(disease: str, keywords: str, limit: int = BATCH_SIZE) -> dict | None:
    """Run a biomcp search article command and return JSON output."""
    cmd = [
        "biomcp", "--json",
        "search", "article",
        "-d", disease,
        "-k", keywords,
        "--limit", str(limit),
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120, encoding="utf-8"
        )
        if result.returncode != 0:
            print(f"  [WARN] biomcp returned {result.returncode}: {result.stderr[:200]}")
            return None
        if not result.stdout.strip():
            return None
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        print("  [WARN] biomcp timed out")
        return None
    except json.JSONDecodeError as e:
        print(f"  [WARN] JSON parse error: {e}")
        return None
    except FileNotFoundError:
        print("[ERROR] biomcp CLI not found. Install with: pip install biomcp-cli")
        sys.exit(1)


def run_biomcp_get(pmid: str) -> dict | None:
    """Fetch full article details by PMID."""
    cmd = ["biomcp", "--json", "get", "article", pmid]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60, encoding="utf-8"
        )
        if result.returncode != 0:
            return None
        if not result.stdout.strip():
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None


def extract_articles_from_search(data: dict) -> list[dict]:
    """Extract article records from biomcp search output (handles multiple formats)."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("articles", "results", "items", "data"):
            if key in data and isinstance(data[key], list):
                return data[key]
        # Might be a single article
        if "pmid" in data or "title" in data:
            return [data]
    return []


def get_article_id(article: dict) -> str | None:
    """Extract a unique identifier from an article record."""
    for key in ("pmid", "PMID", "id", "doi", "DOI"):
        if key in article and article[key]:
            return str(article[key])
    return None


def main():
    print(f"Target: ~{TARGET_COUNT} diabetes papers")
    print(f"Output: {OUTPUT_DIR}")
    print(f"Queries planned: {len(SEARCH_QUERIES)}")
    print("-" * 60)

    all_articles: dict[str, dict] = {}  # id -> article data (dedup)
    failed_queries = []

    for i, query in enumerate(SEARCH_QUERIES, 1):
        if len(all_articles) >= TARGET_COUNT:
            print(f"\n  Reached target ({len(all_articles)} papers). Stopping.")
            break

        disease = query["disease"]
        keywords = query["keywords"]
        print(f"\n[{i}/{len(SEARCH_QUERIES)}] Searching: {disease} + {keywords} ...")

        data = run_biomcp_search(disease, keywords, limit=BATCH_SIZE)
        if data is None:
            failed_queries.append(query)
            continue

        articles = extract_articles_from_search(data)
        new_count = 0
        for article in articles:
            aid = get_article_id(article)
            if aid and aid not in all_articles:
                all_articles[aid] = article
                new_count += 1

        print(f"  Found {len(articles)} articles, {new_count} new. Total: {len(all_articles)}")

        # Rate-limit courtesy (PubMed allows 3 req/sec without key, 10 with)
        time.sleep(2)

    # If we haven't reached target, try fetching more with broader queries
    if len(all_articles) < TARGET_COUNT:
        extra_queries = [
            {"disease": "diabetes", "keywords": "clinical trial 2024"},
            {"disease": "diabetes", "keywords": "clinical trial 2025"},
            {"disease": "diabetes", "keywords": "review 2024"},
            {"disease": "diabetes", "keywords": "review 2025"},
            {"disease": "diabetes", "keywords": "meta-analysis"},
            {"disease": "diabetes", "keywords": "randomized controlled"},
            {"disease": "diabetes", "keywords": "cohort study"},
            {"disease": "diabetes", "keywords": "pancreas islet"},
            {"disease": "diabetes", "keywords": "incretin"},
            {"disease": "diabetes", "keywords": "tirzepatide"},
            {"disease": "diabetes", "keywords": "semaglutide"},
            {"disease": "diabetes", "keywords": "dapagliflozin"},
            {"disease": "diabetes", "keywords": "empagliflozin"},
            {"disease": "diabetes", "keywords": "pioglitazone"},
            {"disease": "diabetes", "keywords": "sulfonylurea"},
        ]
        print(f"\n{'='*60}")
        print(f"Running extra queries to reach {TARGET_COUNT}...")

        for i, query in enumerate(extra_queries, 1):
            if len(all_articles) >= TARGET_COUNT:
                break
            disease = query["disease"]
            keywords = query["keywords"]
            print(f"\n  [Extra {i}/{len(extra_queries)}] {disease} + {keywords} ...")

            data = run_biomcp_search(disease, keywords, limit=BATCH_SIZE)
            if data is None:
                continue

            articles = extract_articles_from_search(data)
            new_count = 0
            for article in articles:
                aid = get_article_id(article)
                if aid and aid not in all_articles:
                    all_articles[aid] = article
                    new_count += 1
            print(f"    Found {len(articles)}, {new_count} new. Total: {len(all_articles)}")
            time.sleep(2)

    # Optionally fetch full details for each paper (slower but richer)
    print(f"\n{'='*60}")
    print(f"Collected {len(all_articles)} unique articles from search phase.")

    # Save search results immediately
    search_output = OUTPUT_DIR / "diabetes_papers_search.json"
    with open(search_output, "w", encoding="utf-8") as f:
        json.dump(list(all_articles.values()), f, indent=2, ensure_ascii=False)
    print(f"Saved search results to: {search_output}")

    # Fetch full details for papers that have a PMID
    print(f"\nFetching full details for papers with PMIDs...")
    detailed_articles = []
    pmids = [aid for aid in all_articles if aid.isdigit()]
    fetch_count = min(len(pmids), TARGET_COUNT)

    for i, pmid in enumerate(pmids[:fetch_count], 1):
        if i % 25 == 0 or i == 1:
            print(f"  Fetching details: {i}/{fetch_count} ...")

        detail = run_biomcp_get(pmid)
        if detail:
            detailed_articles.append(detail)
        else:
            # Keep the search-phase data if full fetch fails
            detailed_articles.append(all_articles[pmid])

        # Rate limit: 1 request per second for unauthenticated
        time.sleep(1.2)

    # Save detailed results
    detail_output = OUTPUT_DIR / "diabetes_papers_detailed.json"
    with open(detail_output, "w", encoding="utf-8") as f:
        json.dump(detailed_articles, f, indent=2, ensure_ascii=False)
    print(f"Saved detailed results to: {detail_output}")

    # Summary
    print(f"\n{'='*60}")
    print(f"DONE")
    print(f"  Total unique papers collected: {len(all_articles)}")
    print(f"  Detailed fetches completed: {len(detailed_articles)}")
    print(f"  Failed queries: {len(failed_queries)}")
    print(f"  Output directory: {OUTPUT_DIR}")
    if failed_queries:
        print(f"  Failed: {[q['keywords'] for q in failed_queries]}")


if __name__ == "__main__":
    main()
