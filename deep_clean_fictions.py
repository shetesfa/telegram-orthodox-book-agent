"""Legacy wrapper - routes directly to unified scripts.audit_and_clean clean-channel."""
import asyncio
from scripts.audit_and_clean import run_clean_channel

if __name__ == "__main__":
    asyncio.run(run_clean_channel(dry_run=False))
