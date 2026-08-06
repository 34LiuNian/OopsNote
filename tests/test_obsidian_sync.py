from __future__ import annotations

import json

from oopsnote.core import AssetStore, DiagramCandidate, DiagramItem, DiagramStatus, Problem, TagStore, TaskCreateRequest, TaskStatus, TaskStore
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


def test_sync_preserves_locally_edited_managed_problem_and_reports_conflict(tmp_path):
    store = TaskStore(tmp_path / "storage")
    syncer = ObsidianSyncer(store, tmp_path / "vaults")
    problem = _problem(store, "original")
    syncer.sync_for_subject("math")
    path = tmp_path / "vaults" / subject_dir("math") / "problems" / problem_filename(problem)
    path.write_text(path.read_text(encoding="utf-8") + "\nLOCAL EDIT", encoding="utf-8")
    task = next(item for item in store.list_all() if item.problem and item.problem.id == problem.id)
    store.update(task.id, problem=problem.model_copy(update={"problem_text": "core update"}))

    report = syncer.sync_for_subject("math")

    assert path.read_text(encoding="utf-8").endswith("LOCAL EDIT")
    assert report.files_written == 0
    assert report.conflicts == [f"problems/{problem_filename(problem)}"]


def test_sync_updates_unchanged_managed_problem_from_core(tmp_path):
    store = TaskStore(tmp_path / "storage")
    syncer = ObsidianSyncer(store, tmp_path / "vaults")
    problem = _problem(store, "original")
    syncer.sync_for_subject("math")
    task = next(item for item in store.list_all() if item.problem and item.problem.id == problem.id)
    updated = problem.model_copy(update={"problem_text": "core update"})
    store.update(task.id, problem=updated)

    report = syncer.sync_for_subject("math")
    path = tmp_path / "vaults" / subject_dir("math") / "problems" / problem_filename(updated)

    assert report.files_written == 1
    assert "core update" in path.read_text(encoding="utf-8")


def test_sync_embeds_the_selected_cached_svg_and_tracks_it_as_managed(tmp_path):
    store = TaskStore(tmp_path / "storage")
    assets = AssetStore(tmp_path / "storage" / "assets")
    syncer = ObsidianSyncer(store, tmp_path / "vaults")
    problem = _problem(store, "diagram problem")
    task = next(item for item in store.list_all() if item.problem and item.problem.id == problem.id)
    svg_path = assets.save_bytes(b"<svg xmlns='http://www.w3.org/2000/svg'/>", "diagram.svg", "diagram")
    candidate = DiagramCandidate(
        ordinal=1,
        tikz_source="\\draw (0,0)--(1,0);",
        svg_path=svg_path,
        pdf_path=assets.save_bytes(b"%PDF-1.4\n%%EOF\n", "diagram.pdf", "diagram"),
        png_path=assets.save_bytes(b"png", "diagram.png", "diagram"),
        decision="accept",
    )
    store.update(task.id, diagram_items=[DiagramItem(
        source_asset_path=task.asset_path,
        status=DiagramStatus.READY_TIKZ,
        selected_candidate_id=candidate.id,
        candidates=[candidate],
    )])

    syncer.sync_for_subject("math")

    subject_root = tmp_path / "vaults" / subject_dir("math")
    note = (subject_root / "problems" / problem_filename(problem)).read_text(encoding="utf-8")
    manifest = json.loads((subject_root / ".oopsnote-managed.json").read_text(encoding="utf-8"))
    assert "![题图](../assets/" in note
    assert len(manifest["asset_files"]) == 1
    assert (subject_root / "assets" / manifest["asset_files"][0]).read_bytes().startswith(b"<svg")


def test_v1_manifest_never_authorizes_overwriting_an_unverified_local_edit(tmp_path):
    store = TaskStore(tmp_path / "storage")
    syncer = ObsidianSyncer(store, tmp_path / "vaults")
    problem = _problem(store, "original")
    syncer.sync_for_subject("math")
    subject_root = tmp_path / "vaults" / subject_dir("math")
    manifest_path = subject_root / ".oopsnote-managed.json"
    v2 = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_path.write_text(
        json.dumps({
            "version": 1,
            "subject": v2["subject"],
            "problem_files": v2["problem_files"],
            "index_files": v2["index_files"],
        }),
        encoding="utf-8",
    )
    path = subject_root / "problems" / problem_filename(problem)
    path.write_text(path.read_text(encoding="utf-8") + "\nLOCAL EDIT", encoding="utf-8")
    task = next(item for item in store.list_all() if item.problem and item.problem.id == problem.id)
    store.update(task.id, problem=problem.model_copy(update={"problem_text": "core update"}))

    report = syncer.sync_for_subject("math")

    assert path.read_text(encoding="utf-8").endswith("LOCAL EDIT")
    assert f"problems/{problem_filename(problem)}" in report.conflicts


def test_sync_preserves_locally_edited_index(tmp_path):
    store = TaskStore(tmp_path / "storage")
    syncer = ObsidianSyncer(store, tmp_path / "vaults")
    problem = _problem(store, "original")
    syncer.sync_for_subject("math")
    index_path = tmp_path / "vaults" / subject_dir("math") / "indexes" / "函数.md"
    index_path.write_text(index_path.read_text(encoding="utf-8") + "\nLOCAL INDEX EDIT", encoding="utf-8")
    task = next(item for item in store.list_all() if item.problem and item.problem.id == problem.id)
    store.update(task.id, problem=problem.model_copy(update={"problem_text": "core update"}))

    report = syncer.sync_for_subject("math")

    assert index_path.read_text(encoding="utf-8").endswith("LOCAL INDEX EDIT")
    assert "indexes/函数.md" in report.conflicts


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


def test_sync_status_update_is_bound_to_the_completed_problem(tmp_path):
    store = TaskStore(tmp_path / "storage")
    syncer = ObsidianSyncer(store, tmp_path / "vaults")
    task = store.create(TaskCreateRequest(subject="math"))
    first = Problem(subject="math", problem_text="first", answer="1", explanation="one")
    store.update(task.id, status=TaskStatus.COMPLETED, problem=first)

    ObsidianSyncQueue._update_tasks(syncer, [(task.id, first.id)], "first synced")
    assert store.get(task.id).stage_message == "first synced"

    second = Problem(subject="math", problem_text="second", answer="2", explanation="two")
    store.update(
        task.id,
        status=TaskStatus.COMPLETED,
        active_run_id=None,
        problem=second,
        stage_message="second completed",
    )
    ObsidianSyncQueue._update_tasks(syncer, [(task.id, first.id)], "late first sync")

    current = store.get(task.id)
    assert current.problem is not None
    assert current.problem.id == second.id
    assert current.stage_message == "second completed"
