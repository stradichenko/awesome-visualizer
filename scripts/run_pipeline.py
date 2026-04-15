#!/usr/bin/env python3
"""Pipeline runner with step-level save points.

Tracks which steps have completed and allows resuming from the last
successful save point instead of re-running the entire pipeline.

Save points work by snapshotting the data directory after each step.
If a step fails or the process is interrupted, resume picks up where
it left off - no wasted API calls or tokens.

Usage:
    python scripts/run_pipeline.py              # Full run (resumes automatically)
    python scripts/run_pipeline.py --from 3     # Start from step 3 (skip 1-2)
    python scripts/run_pipeline.py --reset      # Clear state, run from scratch
    python scripts/run_pipeline.py --status     # Show current pipeline state
    python scripts/run_pipeline.py --dry-run    # Show what would run

Requires GITHUB_TOKEN for steps 1-2.
"""

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "site" / "data"
CHECKPOINT_DIR = DATA_DIR / ".pipeline"
STATE_FILE = CHECKPOINT_DIR / "state.json"

STEPS = [
    {
        "num": 1,
        "name": "fetch_data",
        "label": "Fetch repository data",
        "script": "scripts/fetch_data.py",
        "needs_token": True,
        "outputs": ["repos.json"],
    },
    {
        "num": 2,
        "name": "fetch_noncanonical",
        "label": "Fetch non-canonical awesome lists",
        "script": "scripts/fetch_noncanonical.py",
        "needs_token": True,
        "outputs": ["repos.json"],
    },
    {
        "num": 3,
        "name": "enrich_data",
        "label": "Enrich search data",
        "script": "scripts/enrich_data.py",
        "needs_token": False,
        "outputs": ["repos.json", "search-meta.json"],
    },
    {
        "num": 4,
        "name": "compute_viz",
        "label": "Compute visualization data",
        "script": "scripts/compute_viz.py",
        "needs_token": False,
        "outputs": ["viz-data.json"],
    },
    {
        "num": 5,
        "name": "split_data",
        "label": "Split data for lazy loading",
        "script": "scripts/split_data.py",
        "needs_token": False,
        "outputs": [
            "index.json",
            "repos-official.json",
            "repos-unofficial.json",
            "repos-noncanonical.json",
            "resources-official.json",
            "resources-unofficial.json",
            "resources-noncanonical.json",
        ],
    },
]


def load_state():
    """Load pipeline state or return a fresh one."""
    if STATE_FILE.exists():
        with STATE_FILE.open() as f:
            return json.load(f)
    return {"completed": {}, "started_at": None, "last_updated": None}


def save_state(state):
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    state["last_updated"] = datetime.now(UTC).isoformat()
    tmp = str(STATE_FILE) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    Path(tmp).replace(STATE_FILE)


def snapshot_outputs(step):
    """Copy step outputs to a checkpoint subdirectory for safe restore."""
    snap_dir = CHECKPOINT_DIR / f"step{step['num']}_{step['name']}"
    snap_dir.mkdir(parents=True, exist_ok=True)
    for fname in step["outputs"]:
        src = DATA_DIR / fname
        if src.exists():
            shutil.copy2(src, snap_dir / fname)


def restore_outputs(step):
    """Restore step outputs from a checkpoint snapshot."""
    snap_dir = CHECKPOINT_DIR / f"step{step['num']}_{step['name']}"
    if not snap_dir.exists():
        return False
    for fname in step["outputs"]:
        src = snap_dir / fname
        if src.exists():
            shutil.copy2(src, DATA_DIR / fname)
    return True


def clear_state():
    """Remove all checkpoint data."""
    if CHECKPOINT_DIR.exists():
        shutil.rmtree(CHECKPOINT_DIR)
    print("Pipeline state cleared.")


def show_status():
    """Print current pipeline state."""
    state = load_state()
    completed = state.get("completed", {})

    if not completed:
        print("No pipeline state found - no steps have been completed.")
        return

    print(f"Pipeline started: {state.get('started_at', 'unknown')}")
    print(f"Last updated:     {state.get('last_updated', 'unknown')}")
    print()

    for step in STEPS:
        key = str(step["num"])
        if key in completed:
            info = completed[key]
            elapsed = info.get("elapsed", "?")
            ts = info.get("completed_at", "")
            marker = "[done]"
            detail = f"  {elapsed}s  ({ts})"
        else:
            marker = "[    ]"
            detail = ""
        print(f"  {marker}  Step {step['num']}: {step['label']}{detail}")

    last_done = max((int(k) for k in completed), default=0)
    if last_done < len(STEPS):
        next_step = STEPS[last_done]
        print(f"\nNext: Step {next_step['num']} - {next_step['label']}")
        print("Run with --resume or just re-run to continue.")
    else:
        print("\nAll steps completed.")


def run_step(step, state):
    """Run a single pipeline step, snapshot on success."""
    num = step["num"]
    print(f"\n{'=' * 60}")
    print(f"  Step {num}/{len(STEPS)}: {step['label']}")
    print(f"{'=' * 60}\n")

    cmd = [sys.executable, str(ROOT / step["script"])]
    t0 = time.monotonic()

    try:
        result = subprocess.run(cmd, cwd=str(ROOT), check=True)
    except subprocess.CalledProcessError as exc:
        elapsed = round(time.monotonic() - t0, 1)
        print(f"\n[pipeline] Step {num} FAILED after {elapsed}s (exit code {exc.returncode})")
        print(f"[pipeline] Resume later with: python scripts/run_pipeline.py")
        save_state(state)
        sys.exit(exc.returncode)
    except KeyboardInterrupt:
        elapsed = round(time.monotonic() - t0, 1)
        print(f"\n[pipeline] Interrupted at step {num} after {elapsed}s")
        print(f"[pipeline] Resume later with: python scripts/run_pipeline.py")
        save_state(state)
        sys.exit(130)

    elapsed = round(time.monotonic() - t0, 1)

    # Save snapshot and mark complete
    snapshot_outputs(step)
    state["completed"][str(num)] = {
        "name": step["name"],
        "completed_at": datetime.now(UTC).isoformat(),
        "elapsed": elapsed,
    }
    save_state(state)

    print(f"\n[pipeline] Step {num} completed in {elapsed}s - save point created")


def main():
    parser = argparse.ArgumentParser(description="Pipeline runner with save points")
    parser.add_argument("--reset", action="store_true", help="Clear all checkpoints and start fresh")
    parser.add_argument("--status", action="store_true", help="Show current pipeline state")
    parser.add_argument("--from", type=int, dest="from_step", metavar="N", help="Force start from step N (1-5)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would run without executing")
    args = parser.parse_args()

    if args.reset:
        clear_state()
        if not args.from_step and not args.dry_run:
            return

    if args.status:
        show_status()
        return

    state = load_state()
    completed = state.get("completed", {})

    # Determine starting step
    if args.from_step:
        start = args.from_step
        if start < 1 or start > len(STEPS):
            print(f"Error: --from must be between 1 and {len(STEPS)}", file=sys.stderr)
            sys.exit(1)
        # When forcing a start point, restore the previous step's outputs
        # so the forced step has valid inputs
        if start > 1:
            prev = STEPS[start - 2]
            prev_key = str(prev["num"])
            if prev_key in completed:
                print(f"[pipeline] Restoring outputs from step {prev['num']} snapshot...")
                if not restore_outputs(prev):
                    print(f"Warning: No snapshot found for step {prev['num']}", file=sys.stderr)
    else:
        # Auto-resume from last completed step
        last_done = max((int(k) for k in completed), default=0)
        start = last_done + 1

        # Restore outputs from the last completed step before continuing
        if last_done > 0:
            prev = STEPS[last_done - 1]
            prev_key = str(prev["num"])
            if prev_key in completed:
                print(f"[pipeline] Restoring outputs from step {prev['num']} snapshot...")
                restore_outputs(prev)

    if start > len(STEPS):
        print("[pipeline] All steps already completed. Use --reset to start over.")
        return

    steps_to_run = [s for s in STEPS if s["num"] >= start]

    if not state.get("started_at"):
        state["started_at"] = datetime.now(UTC).isoformat()

    if args.dry_run:
        print("[pipeline] Dry run - would execute:\n")
        for step in steps_to_run:
            key = str(step["num"])
            status = "SKIP (done)" if key in completed and step["num"] < start else "RUN"
            print(f"  Step {step['num']}: {step['label']}  [{status}]")
        return

    skipped = start - 1
    if skipped > 0:
        print(f"[pipeline] Resuming from step {start} ({skipped} step(s) already done)")
    else:
        print(f"[pipeline] Starting fresh pipeline run ({len(STEPS)} steps)")

    total_t0 = time.monotonic()

    for step in steps_to_run:
        run_step(step, state)

    total_elapsed = round(time.monotonic() - total_t0, 1)
    print(f"\n{'=' * 60}")
    print(f"  Pipeline complete - {len(steps_to_run)} steps in {total_elapsed}s")
    print(f"{'=' * 60}")

    # Clean up checkpoints after full success
    print("[pipeline] Cleaning up checkpoint snapshots...")
    clear_state()


if __name__ == "__main__":
    main()
