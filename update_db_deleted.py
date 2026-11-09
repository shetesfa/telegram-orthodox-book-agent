"""Legacy wrapper - routes directly to unified scripts.audit_and_clean clean-db."""
import asyncio
from scripts.audit_and_clean import run_clean_db

if __name__ == "__main__":
    asyncio.run(run_clean_db())
