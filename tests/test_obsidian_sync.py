from __future__ import annotations

from oopsnote.core import Problem, TagStore, TaskCreateRequest, TaskStore
from oopsnote.obsidian.syncer import MANAGED_MARKER, ObsidianSyncQueue, ObsidianSyncer
from oopsnote.obsidian.writer import problem_filename, subject_dir


def _problem(store: TaskStore, text: str) -> Problem:
    task = store.create(TaskCreateRequest(subject="math"))
    updated = store.set_problem(
        task.id,
        Problem(
            subject="math",
            problem_text=text,
            answer="1",
            explanation="test",
            knowledge_points=["函数"],
        ),
    )
    return updated.problem


def test_incremental_sync_does_not_rewrite_existing_problem_note(tmp_path):
    store = TaskStore(tmp_path / "storage")
    tags = TagStore(tmp_path / "storage" / "tags.json")
    syncer = ObsidianSyncer(store, tmp_path / "vaults", tags)
    first = _problem(store, "first")
    syncer.sync_for_subject("math")
    first_path = (
        tmp_path / "vaults" / subject_dir("math") / "problems" / problem_filename(first)
    )
    first_path.write_text(first_path.read_text(encoding="utf-8") + "\nLOCAL EDIT", encoding="utf-8")

    second = _problem(store, "second")
    report = syncer.sync_problem(second)

    assert report.files_written == 1
    assert first_path.read_text(encoding="utf-8").endswith("LOCAL EDIT")
    second_path = first_path.with_name(problem_filename(second))
    assert MANAGED_MARKER in second_path.read_text(encoding="utf-8")


def test_sync_cleanup_removes_only_manifest_owned_files(tmp_path):
    store = TaskStore(tmp_path / "storage")
    syncer = ObsidianSyncer(store, tmp_path / "vaults")
    problem = _problem(store, "managed")
    syncer.sync_for_subject("math")
    subject_root = tmp_path / "vaults" / subject_dir("math")
    managed_path = subject_root / "problems" / problem_filename(problem)
    personal_path = subject_root / "problems" / "personal-note.md"
    personal_path.write_text("# My note", encoding="utf-8")
    task = next(task for task in store.list_all() if task.problem and task.problem.id == problem.id)
    store.delete(task.id)

    report = syncer.sync_for_subject("math")

    assert report.files_removed >= 1
    assert not managed_path.exists()
    assert personal_path.read_text(encoding="utf-8") == "# My note"


def test_sync_queue_coalesces_same_subject_without_losing_problems(tmp_path):
    store = TaskStore(tmp_path / "storage")
    syncer = ObsidianSyncer(store, tmp_path / "vaults")
    problems = [_problem(store, f"problem {index}") for index in range(3)]
    queue = ObsidianSyncQueue()

    with queue._condition:
        for problem in problems:
            queue.enqueue(syncer, problem)
        _, (_, pending) = queue._pending.popitem()

    assert set(pending) == {problem.id for problem in problems}

    syncer.sync_problems([problem for problem, _ in pending.values()])
    problem_dir = tmp_path / "vaults" / subject_dir("math") / "problems"
    assert {
        problem_filename(problem) for problem in problems
    } <= {path.name for path in problem_dir.glob("*.md")}
