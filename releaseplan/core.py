"""Deterministic impact planning over explicit service dependency graphs."""

from collections import deque


class GraphError(ValueError):
    """The supplied graph is invalid."""


class CycleError(GraphError):
    def __init__(self, blocked):
        self.blocked = sorted(blocked)
        super().__init__("Cycle prevents planning; blocked services: " + ", ".join(self.blocked))


def validate(raw):
    """Copy/validate {service: [dependencies]}; all names must be declared."""
    if not isinstance(raw, dict) or not raw:
        raise GraphError("graph must be a non-empty object")
    if any(not isinstance(name, str) or not name.strip() for name in raw):
        raise GraphError("service names must be non-blank strings")
    graph = {}
    for name, dependencies in raw.items():
        if not isinstance(dependencies, list):
            raise GraphError(f"{name}: dependencies must be a list")
        if any(not isinstance(d, str) for d in dependencies):
            raise GraphError(f"{name}: dependency names must be strings")
        if len(set(dependencies)) != len(dependencies):
            raise GraphError(f"{name}: duplicate dependencies")
        if name in dependencies:
            raise GraphError(f"{name}: cannot depend on itself")
        missing = set(dependencies) - raw.keys()
        if missing:
            raise GraphError(f"{name}: undeclared dependencies {sorted(missing)}")
        graph[name] = frozenset(dependencies)
    return graph


def layers(graph, selected=None):
    """Kahn layers; dependencies precede consumers. Input is validated by plan()."""
    remaining = set(graph) if selected is None else set(selected)
    result = []
    done = set(graph) - remaining
    while remaining:
        ready = sorted(name for name in remaining if graph[name] <= done)
        if not ready:
            raise CycleError(remaining)
        result.append(ready)
        done.update(ready)
        remaining.difference_update(ready)
    return result


def plan(raw, changed):
    """Validate the whole graph, find reverse closure, return rebuild/test batches.

    This is NOT a deployment executor. Unchanged dependencies are assumed available.
    """
    graph = validate(raw)
    layers(graph)  # Reject cycles even in an unrelated component.
    if not isinstance(changed, list) or any(not isinstance(n, str) for n in changed):
        raise GraphError("changed must be a list of service names")
    unknown = set(changed) - graph.keys()
    if unknown:
        raise GraphError(f"unknown changed services: {sorted(unknown)}")
    reverse = {name: set() for name in graph}
    for consumer, deps in graph.items():
        for dependency in deps:
            reverse[dependency].add(consumer)
    affected = set(changed)
    queue = deque(sorted(affected))
    while queue:
        for consumer in sorted(reverse[queue.popleft()]):
            if consumer not in affected:
                affected.add(consumer)
                queue.append(consumer)
    batches = layers(graph, affected)
    return {
        "changed": sorted(set(changed)),
        "affected": sorted(affected),
        "unaffected": sorted(graph.keys() - affected),
        "batches": batches,
        "external_prerequisites": sorted(
            {dependency for name in affected for dependency in graph[name]} - affected
        ),
    }
