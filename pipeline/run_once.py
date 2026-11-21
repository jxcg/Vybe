"""Trigger one vybe-refresh execution and wait for it (the worker must be running).

uv run --env-file .env python -m pipeline.run_once --lat 51.5136 --lng -0.1365
"""

import argparse
import os

from mistralai.client import Mistral


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lat", type=float, default=51.5136, help="latitude (default: Soho)")
    ap.add_argument("--lng", type=float, default=-0.1365, help="longitude (default: Soho)")
    ap.add_argument("--workflow", default="vybe-refresh", help="vybe-refresh | vybe-theme")
    args = ap.parse_args()
    client = Mistral(api_key=os.environ["MISTRAL_API_KEY"])
    execution = client.workflows.execute_workflow(
        workflow_identifier=args.workflow,
        input={"lat": args.lat, "lng": args.lng},
        wait_for_result=True,
    )
    print(execution.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
