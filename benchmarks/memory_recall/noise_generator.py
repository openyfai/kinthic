"""Generate seeded distractor memories for the recall benchmark."""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta, timezone

from silex.models.schemas import Memory, MemorySource, MemoryType

TOPICS = [
    "authentication",
    "billing",
    "dashboard",
    "notifications",
    "search",
    "analytics",
    "onboarding",
    "permissions",
    "webhooks",
    "caching",
]
MODULES = ["auth", "billing", "api", "worker", "frontend", "ingest"]
TOOLS = ["vim", "vscode", "neovim", "emacs", "zed"]
ALTS = ["nano", "sublime", "atom", "idea"]
TASKS = ["editing", "debugging", "refactoring", "reviewing"]
PEOPLE = ["Jordan", "Taylor", "Morgan", "Casey", "Riley", "Quinn"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
MONTHS = ["January", "March", "June", "September", "November"]
SERVICES = ["DNS", "CDN", "monitoring", "logging", "CI"]
SUITES = ["unit", "integration", "e2e", "smoke"]
FILES = ["handler.py", "routes.ts", "worker.go", "schema.sql", "config.yaml"]
PATTERNS = ["helper", "middleware", "adapter", "factory"]


def _fill_template(template: str, rng: random.Random) -> str:
    return template.format(
        topic=rng.choice(TOPICS),
        day=rng.choice(DAYS),
        module=rng.choice(MODULES),
        metric=rng.choice(["latency", "throughput", "reliability", "coverage"]),
        tool=rng.choice(TOOLS),
        alt=rng.choice(ALTS),
        task=rng.choice(TASKS),
        person=rng.choice(PEOPLE),
        code=rng.randint(200, 599),
        time=f"{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}",
        file=rng.choice(FILES),
        pattern=rng.choice(PATTERNS),
        service=rng.choice(SERVICES),
        month=rng.choice(MONTHS),
        suite=rng.choice(SUITES),
        count=rng.randint(12, 400),
    )


def generate_noise_memories(
    count: int,
    templates: list[str],
    seed: int,
    *,
    max_age_days: int = 30,
) -> list[Memory]:
    """Return `count` distractor Memory objects with staggered ages."""
    rng = random.Random(seed)
    now = datetime.now(timezone.utc)
    memories: list[Memory] = []

    for i in range(count):
        template = rng.choice(templates)
        content = _fill_template(template, rng)
        # Avoid accidental needle tokens
        if "NEEDLE_" in content:
            content = content.replace("NEEDLE_", "NOTE_")

        age_days = rng.uniform(0, max_age_days)
        ts = now - timedelta(days=age_days, hours=rng.randint(0, 23))
        iso = ts.isoformat()

        mem = Memory(
            id=str(uuid.uuid4()),
            content=content,
            source=MemorySource.USER,
            memory_type=MemoryType.SEMANTIC,
            importance=round(rng.uniform(0.2, 0.7), 2),
            confidence=0.5,
            tags=["benchmark_noise"],
        )
        mem.created_at = iso
        mem.last_accessed = iso
        memories.append(mem)

    return memories
