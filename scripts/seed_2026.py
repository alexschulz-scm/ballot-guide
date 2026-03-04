"""Seed FL-2026-GEN ballot data for development/demo."""
import json
import sqlite3
import sys
import os

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(_REPO_ROOT, "data", "ballot-guide.db")


def seed_2026(db_path: str = DB_PATH) -> None:
    conn = sqlite3.connect(db_path)

    # Races
    races = [
        ("FL-2026-GOV", "FL-2026-GEN", "state_executive", "Governor of Florida", "statewide"),
        ("FL-2026-SEN", "FL-2026-GEN", "federal", "U.S. Senate - Florida", "statewide"),
        ("FL-2026-M1", "FL-2026-GEN", "ballot_measure", "Amendment 1: Homestead Property Tax Exemption", None),
        ("FL-2026-M2", "FL-2026-GEN", "ballot_measure", "Amendment 2: Right to Clean Water", None),
        ("FL-2026-M3", "FL-2026-GEN", "ballot_measure", "Amendment 3: Education Funding Guarantee", None),
    ]
    for r in races:
        conn.execute(
            "INSERT OR IGNORE INTO races (id, election_id, race_type, title, district) VALUES (?,?,?,?,?)", r
        )

    # Measures
    src = json.dumps([{
        "name": "Florida Division of Elections",
        "url": "https://dos.myflorida.com",
        "bias_rating": None,
        "fetched_at": "2026-03-03T00:00:00Z",
    }])

    measures = [
        (
            "FL-2026-M1-meas", "FL-2026-M1", "Homestead Tax Exemption",
            "Increase homestead property tax exemption from $50,000 to $75,000 for primary residences",
            None, None,
            "Estimated $1.4 billion annual reduction in local government revenue",
            "Florida Revenue Estimating Conference",
            "Provides property tax relief for homeowners, making housing more affordable",
            "Reduces local government revenue needed for schools, roads, and emergency services",
            json.dumps(["housing", "taxes"]),
            None, None, None, src, None, None, None, "full",
        ),
        (
            "FL-2026-M2-meas", "FL-2026-M2", "Right to Clean Water",
            "Enshrine the right to clean and healthy water in the Florida Constitution",
            None, None,
            "Potential compliance costs of $500M-$2B over 10 years",
            "Florida Department of Environmental Protection",
            "Protects waterways from pollution and holds polluters accountable",
            "Could increase regulatory burden on agriculture and development",
            json.dumps(["environment", "healthcare"]),
            None, None, None, src, None, None, None, "full",
        ),
        (
            "FL-2026-M3-meas", "FL-2026-M3", "Education Funding Guarantee",
            "Require the state to fund public schools at or above the national per-pupil average",
            None, None,
            "Estimated $3.2 billion annual increase in state education spending",
            "Florida Office of Economic and Demographic Research",
            "Ensures Florida students receive adequate funding comparable to national standards",
            "Would require significant tax increases or cuts to other state programs",
            json.dumps(["education", "taxes"]),
            None, None, None, src, None, None, None, "full",
        ),
    ]
    for m in measures:
        conn.execute(
            "INSERT OR IGNORE INTO measures "
            "(id, race_id, short_title, full_title, measure_text, plain_summary, "
            "fiscal_impact, fiscal_impact_source, proponent_argument, opponent_argument, "
            "topic_tags_json, passed, yes_pct, no_pct, sources_json, "
            "ballotpedia_url, fl_elections_url, fetched_at, data_completeness) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            m,
        )

    # Candidates
    candidates = [
        (
            "cand_gov_dem_2026", "FL-2026-GOV", "Nikki Fried", "Democratic",
            "Former Florida Agriculture Commissioner",
            json.dumps({
                "housing": "Supports expanding affordable housing programs and rent stabilization",
                "education": "Advocates for increased public school funding and teacher pay raises",
                "taxes": "Supports progressive tax reform and closing corporate loopholes",
                "healthcare": "Supports Medicaid expansion under the ACA",
                "environment": "Prioritizes Everglades restoration and clean energy transition",
            }),
            None, None, None, None, "full",
        ),
        (
            "cand_gov_rep_2026", "FL-2026-GOV", "Jimmy Patronis", "Republican",
            "Current Florida CFO and former state legislator",
            json.dumps({
                "housing": "Supports reducing regulations to increase housing supply",
                "education": "Champions school choice and parental rights in education",
                "taxes": "Opposes state income tax, supports further tax cuts for businesses",
                "economy": "Focuses on deregulation and business-friendly policies",
                "public_safety": "Supports increased law enforcement funding",
            }),
            None, None, None, None, "full",
        ),
        (
            "cand_sen_dem_2026", "FL-2026-SEN", "Debbie Mucarsel-Powell", "Democratic",
            "Former U.S. Representative for Florida District 26",
            json.dumps({
                "housing": "Supports federal affordable housing investment",
                "education": "Advocates for student loan reform and Pell Grant expansion",
                "healthcare": "Supports strengthening the ACA and lowering drug costs",
                "environment": "Supports climate action and coastal resilience funding",
                "economy": "Focuses on small business support and worker protections",
            }),
            None, None, None, None, "full",
        ),
        (
            "cand_sen_rep_2026", "FL-2026-SEN", "Rick Scott", "Republican",
            "Incumbent U.S. Senator, former Florida Governor",
            json.dumps({
                "taxes": "Opposes tax increases, supports extending Trump-era tax cuts",
                "economy": "Emphasizes fiscal responsibility and reducing federal spending",
                "public_safety": "Supports increased border security funding",
                "healthcare": "Supports market-based healthcare solutions",
                "infrastructure": "Supports public-private partnerships for infrastructure",
            }),
            None, None, None, None, "full",
        ),
    ]
    for c in candidates:
        conn.execute(
            "INSERT OR IGNORE INTO candidates "
            "(id, race_id, name, party, bio, positions_json, funding_summary_json, "
            "ballotpedia_url, fl_elections_url, fetched_at, data_completeness) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            c,
        )

    conn.commit()

    # Verify
    count = conn.execute(
        "SELECT COUNT(*) FROM races WHERE election_id = 'FL-2026-GEN'"
    ).fetchone()[0]
    print(f"FL-2026-GEN: {count} races seeded")
    conn.close()


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else DB_PATH
    seed_2026(path)
    print("Done.")
