import copy
import json

import pytest

from releaseplan.cli import main
from releaseplan.core import CycleError, GraphError, plan


@pytest.fixture
def graph():
    return {"db": [], "api": ["db"], "worker": ["db"], "web": ["api"], "docs": []}


def test_reverse_transitive_closure(graph):
    result = plan(graph, ["db"])
    assert result["affected"] == ["api", "db", "web", "worker"]
    assert result["batches"] == [["db"], ["api", "worker"], ["web"]]
    assert result["unaffected"] == ["docs"]


def test_leaf_change_does_not_rebuild_dependencies(graph):
    result = plan(graph, ["web"])
    assert result["affected"] == ["web"]
    assert result["external_prerequisites"] == ["api"]


def test_shared_dependency_is_only_once():
    result = plan({"a": [], "b": ["a"], "c": ["a"], "d": ["b", "c"]}, ["a"])
    assert result["batches"] == [["a"], ["b", "c"], ["d"]]


def test_multiple_changes_deduplicated(graph):
    assert plan(graph, ["api", "api", "db"]) == plan(graph, ["db", "api"])


def test_no_changes(graph):
    result = plan(graph, [])
    assert result["batches"] == []
    assert result["affected"] == []
    assert result["unaffected"] == sorted(graph)


def test_input_unmodified(graph):
    before = copy.deepcopy(graph)
    plan(graph, ["db"])
    assert graph == before


def test_order_independent(graph):
    assert plan(dict(reversed(list(graph.items()))), ["db"]) == plan(graph, ["db"])


def test_cycle_and_downstream_diagnostic():
    with pytest.raises(CycleError) as exc:
        plan({"a": ["b"], "b": ["a"], "c": ["a"]}, ["a"])
    assert exc.value.blocked == ["a", "b", "c"]


def test_unrelated_cycle_rejected():
    with pytest.raises(CycleError):
        plan({"x": [], "a": ["b"], "b": ["a"]}, ["x"])


@pytest.mark.parametrize(
    "raw",
    [
        {},
        [],
        {"": []},
        {"a": "b"},
        {"a": [4]},
        {"a": ["missing"]},
        {"a": ["a"]},
        {"a": ["b", "b"], "b": []},
    ],
)
def test_invalid_graph(raw):
    with pytest.raises(GraphError):
        plan(raw, [])


@pytest.mark.parametrize("changed", [["missing"], "api", [1], None])
def test_invalid_changes(graph, changed):
    with pytest.raises(GraphError):
        plan(graph, changed)


def test_all_edges_respect_batches(graph):
    batches = plan(graph, list(graph))["batches"]
    position = {n: i for i, batch in enumerate(batches) for n in batch}
    assert all(position[d] < position[n] for n, deps in graph.items() for d in deps)


def test_large_chain():
    graph = {str(i): [str(i - 1)] if i else [] for i in range(300)}
    assert len(plan(graph, ["0"])["batches"]) == 300


def test_cli_success(tmp_path, capsys):
    path = tmp_path / "graph.json"
    path.write_text('{"api": []}')
    assert main([str(path), "--changed", "api"]) == 0
    assert json.loads(capsys.readouterr().out)["batches"] == [["api"]]


@pytest.mark.parametrize("contents", ["{", '{"api": ["no"]}', "[]"])
def test_cli_error(tmp_path, capsys, contents):
    path = tmp_path / "graph.json"
    path.write_text(contents)
    assert main([str(path)]) == 2
    assert "error" in json.loads(capsys.readouterr().err)


def test_cli_missing_file(tmp_path, capsys):
    assert main([str(tmp_path / "absent")]) == 2
    assert "error" in json.loads(capsys.readouterr().err)
