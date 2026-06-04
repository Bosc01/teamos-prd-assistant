"""Shared configuration for pipeline defaults."""

from __future__ import annotations

import os

DEFAULT_N_CLUSTERS = 15


def default_cluster_count() -> int:
    raw = os.getenv("TOPIC_CLUSTER_COUNT", str(DEFAULT_N_CLUSTERS)).strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_N_CLUSTERS
