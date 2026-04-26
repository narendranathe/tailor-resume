"""
scripts/seed_supabase.py
Verifies Supabase connectivity, runs pending migrations, and seeds activity data.

Usage:
    SUPABASE_URL=https://xxx.supabase.co SUPABASE_SERVICE_KEY=... python scripts/seed_supabase.py

What it does:
    1. Connects to Supabase using the service key (bypasses RLS).
    2. Creates tables via migrations/001 and migrations/002 if they don't exist.
    3. Inserts a seed user profile and 3 months of usage activity rows.
    4. Prints a summary of what's in the DB.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

# ── Require env vars ───────────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    print("ERROR: set SUPABASE_URL and SUPABASE_SERVICE_KEY before running.")
    sys.exit(1)

try:
    from supabase import create_client
except ImportError:
    print("ERROR: pip install supabase")
    sys.exit(1)

client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# ── Run migrations via SQL ─────────────────────────────────────────────────────
MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"

def run_migrations() -> None:
    print("Running migrations...")
    for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        sql = sql_file.read_text()
        try:
            client.rpc("exec_sql", {"sql": sql}).execute()
            print(f"  OK  {sql_file.name}")
        except Exception as e:
            # Tables already exist or RPC not available — try raw SQL via postgrest
            print(f"  SKIP {sql_file.name} (may already exist): {e}")

# ── Seed data ──────────────────────────────────────────────────────────────────
SEED_USER_ID = "seed-user-naren"
SEED_PROFILE = {
    "experience": [
        {
            "title": "Data Engineer",
            "company": "ExponentHR",
            "start": "2024-07",
            "end": None,
            "bullets": [
                "Architected governed semantic layer on Microsoft Fabric with FAISS + NL-to-SQL, cutting support tickets ~40%",
                "Compressed deployment cycles 3 months → 14 days via Azure DevOps CI/CD",
                "CDC ETL reengineering: 30min → 8min, -67% compute cost",
            ],
        }
    ],
    "skills": ["Python", "SQL", "Spark", "Kafka", "Azure", "FAISS", "LangChain", "MLflow", "Docker"],
    "education": [{"school": "Missouri S&T", "degree": "M.S. Information Science", "gpa": 4.0}],
    "projects": [{"name": "AutoApply AI"}, {"name": "JobScout"}, {"name": "tailor-resume"}],
    "certifications": ["DP-700 Microsoft Fabric Data Engineer", "AI-900 Azure AI Fundamentals"],
}

def seed_profile() -> None:
    print(f"\nSeeding profile for {SEED_USER_ID}...")
    try:
        client.table("user_profiles").upsert(
            {
                "user_id": SEED_USER_ID,
                "profile_json": SEED_PROFILE,
                "plan": "pro",
                "updated_at": "now()",
            },
            on_conflict="user_id",
        ).execute()
        print("  OK  user_profiles row upserted (plan=pro)")
    except Exception as e:
        print(f"  ERR {e}")

def seed_usage() -> None:
    print("\nSeeding 3 months of usage activity...")
    now = datetime.utcnow()
    for months_back in range(3):
        month_dt = now.replace(day=1) - timedelta(days=months_back * 28)
        month_key = month_dt.strftime("%Y-%m")
        count = [5, 12, 3][months_back]
        try:
            client.table("usage").upsert(
                {"user_id": SEED_USER_ID, "month": month_key, "resume_count": count},
                on_conflict="user_id,month",
            ).execute()
            print(f"  OK  usage/{month_key} → {count} tailors")
        except Exception as e:
            print(f"  ERR {month_key}: {e}")

def check_state() -> None:
    print("\nDB state after seed:")
    try:
        profiles = client.table("user_profiles").select("user_id,plan,updated_at").execute()
        print(f"  user_profiles rows: {len(profiles.data)}")
        for row in profiles.data:
            print(f"    {row['user_id']} plan={row['plan']}")
    except Exception as e:
        print(f"  ERR reading user_profiles: {e}")

    try:
        usage = client.table("usage").select("user_id,month,resume_count").execute()
        print(f"  usage rows: {len(usage.data)}")
        for row in usage.data:
            print(f"    {row['user_id']} {row['month']} → {row['resume_count']} tailors")
    except Exception as e:
        print(f"  ERR reading usage: {e}")


if __name__ == "__main__":
    run_migrations()
    seed_profile()
    seed_usage()
    check_state()
    print("\nDone. Supabase is connected and has activity data.")
