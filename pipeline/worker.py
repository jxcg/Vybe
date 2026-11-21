"""Run the Vybe pipeline worker: registers the workflows and waits for executions.

    DEPLOYMENT_NAME=vybe-hackathon uv run --env-file .env python -m pipeline.worker

The worker connects to Mistral with MISTRAL_API_KEY, so executions show up in Studio.
"""

import asyncio
import logging

from mistralai.workflows import discover_all_workflows_in_package, run_worker


async def main() -> None:
    workflows = discover_all_workflows_in_package(
        "pipeline", skip_modules={"pipeline.worker", "pipeline.run_once"}
    )
    # importing pipeline.agents pulls in mistralai.agents, which raises the root
    # logger to WARNING and drops its handlers — restore INFO so the worker logs
    logging.basicConfig(level=logging.INFO, force=True)
    await run_worker(workflows)


if __name__ == "__main__":
    asyncio.run(main())
