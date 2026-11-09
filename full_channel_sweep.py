"""Legacy wrapper - routes directly to unified scripts.audit_and_clean sweep-and-forward."""
import asyncio
from scripts.audit_and_clean import run_sweep_and_forward

if __name__ == "__main__":
    asyncio.run(run_sweep_and_forward())
