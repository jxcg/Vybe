"""Run the Vybe pipeline worker: registers the workflows and waits for executions.

    uv run --env-file .env python -m pipeline.worker

The worker connects to Mistral with MISTRAL_API_KEY, so executions show up in Studio.
"""

import asyncio

from mistralai.workflows import discover_all_workflows_in_package, run_worker


async def main() -> None:
    workflows = discover_all_workflows_in_package(
        "pipeline", skip_modules={"pipeline.worker", "pipeline.run_once"}
    )
    await run_worker(workflows)


if __name__ == "__main__":
    asyncio.run(main())
