"""Shared constants and helpers for the data pipeline.

Single source of truth for health scoring, bucket definitions, and
configuration values used by multiple scripts.
"""

from datetime import UTC, datetime

# --------------- Rate limiting / batching ---------------
BATCH_SIZE = 30          # Lighter queries reduce GitHub 502 rate
BATCH_RETRIES = 3        # Rounds of sequential retry for failed batches
MAX_RETRIES = 5          # Per-request retry attempts (exponential backoff)
RETRY_DELAY = 3          # Base delay in seconds (3/6/12/24/48s)
GQL_DELAY = 1.0          # Pause between sequential batch retries

# --------------- Health score thresholds ---------------
# Each factor contributes a sub-score to a 0-100 total.
#
# Factor breakdown (max total = 100):
#   Stars:            20 pts
#   Commits (90d):    20 pts
#   Recency:          20 pts
#   PR activity:       8 pts  (open PRs signal active development)
#   Fork engagement:   7 pts  (fork-to-star ratio signals community use)
#   License:           8 pts
#   Description:       7 pts
#   Not archived:     10 pts

STAR_TIERS = [
    (10000, 20),
    (1000, 16),
    (100, 12),
    (10, 6),
    (0, 2),
]

COMMIT_TIERS = [
    (50, 20),
    (20, 16),
    (5, 12),
    (1, 6),
]

RECENCY_TIERS = [
    (30, 20),
    (90, 16),
    (180, 12),
    (365, 6),
]
RECENCY_FALLBACK = 2

# Open PRs show active collaboration
PR_TIERS = [
    (20, 8),
    (5, 6),
    (1, 4),
]

# Fork-to-star ratio shows downstream adoption
FORK_RATIO_TIERS = [
    (0.25, 7),
    (0.10, 5),
    (0.05, 3),
    (0.01, 1),
]

LICENSE_SCORE = 8
DESCRIPTION_SCORE = 7
NOT_ARCHIVED_SCORE = 10

# --------------- Bucket definitions ---------------
HEALTH_BUCKETS = [
    ("0-19", 0, 19),
    ("20-39", 20, 39),
    ("40-59", 40, 59),
    ("60-79", 60, 79),
    ("80-100", 80, 100),
]

STAR_BUCKETS = [
    ("0-100", 0, 100),
    ("101-500", 101, 500),
    ("501-1k", 501, 1000),
    ("1k-5k", 1001, 5000),
    ("5k-10k", 5001, 10000),
    ("10k-50k", 10001, 50000),
    ("50k+", 50001, float("inf")),
]


def compute_health(rec):
    """Compute a 0-100 health score from repo metrics."""
    score = 0

    stars = rec.get("stars", 0)
    for threshold, points in STAR_TIERS:
        if stars >= threshold:
            score += points
            break

    c90 = rec.get("commits_90d", 0)
    for threshold, points in COMMIT_TIERS:
        if c90 >= threshold:
            score += points
            break

    push = rec.get("last_push", "")
    if push:
        try:
            dt = datetime.fromisoformat(push.replace("Z", "+00:00"))
            days = (datetime.now(UTC) - dt).days
            for max_days, points in RECENCY_TIERS:
                if days <= max_days:
                    score += points
                    break
            else:
                score += RECENCY_FALLBACK
        except (ValueError, TypeError):
            pass

    # PR activity - open PRs signal active collaboration
    open_prs = rec.get("open_prs", 0)
    for threshold, points in PR_TIERS:
        if open_prs >= threshold:
            score += points
            break

    # Fork engagement - fork/star ratio signals downstream adoption
    if stars > 0:
        forks = rec.get("forks", 0)
        ratio = forks / stars
        for threshold, points in FORK_RATIO_TIERS:
            if ratio >= threshold:
                score += points
                break

    if rec.get("license"):
        score += LICENSE_SCORE
    if rec.get("description"):
        score += DESCRIPTION_SCORE
    if not rec.get("is_archived", False):
        score += NOT_ARCHIVED_SCORE

    return min(score, 100)
