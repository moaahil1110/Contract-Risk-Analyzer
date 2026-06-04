"""Mark stale queued/running/retrying analysis jobs as failed."""

import asyncio
import json
import sys

from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from db.queries import mark_stale_analysis_jobs_failed  # noqa: E402


async def main() -> None:
    timeout_minutes = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    jobs = await mark_stale_analysis_jobs_failed(timeout_minutes)
    print(json.dumps({
        "timeout_minutes": timeout_minutes,
        "failed_job_count": len(jobs),
        "jobs": jobs,
    }, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
