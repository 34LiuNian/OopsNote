from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from oopsnote.api import main
from oopsnote.api.routes.papers import _expanded_knowledge_tags
from oopsnote.core import (
    ContentFormat,
    PaperDraft,
    PaperDraftCreateRequest,
    PaperDraftItem,
    PaperDraftStore,
    Problem,
    QuestionType,
    TaskCreateRequest,
    TaskRecord,
    TaskStore,
)
from oopsnote.paper import (
    PaperCompileError,
    PaperCompileFailure,
    PaperDocumentError,
    build_paper_bundle,
    build_paper_document,
    build_paper_tex,
    compile_paper_pdf,
    infer_difficulty_coefficients,
    select_paper_items,
)


def test_top_level_knowledge_node_includes_its_descendants(monkeypatch):
    class KnowledgeTreeStore:
        def knowledge_tree(self, subject: str):
            assert subject == "math"
            return {
                "subjects": {
                    "math": {
                        "root": {
                            "id": "root",
                            "title": "高中数学",
                            "scope": "core",
                            "selectable": False,
                            "children": [
                                {
                                    "id": "top-level",
                                    "title": "推理与证明",
                                    "scope": "core",
                                    "selectable": False,
                                    "children": [
                                        {
                                            "id": "leaf",
                                            "title": "直接证明与间接证明",
                                            "scope": "core",
                                            "selectable": True,
                                            "children": [],
                                        }
                                    ],
                                }
                            ],
                        }
                    }
                }
            }

    monkeypatch.setattr(main, "TAG_STORE", KnowledgeTreeStore())

    assert _expanded_knowledge_tags("math", ["top-level"], []) == [
        "推理与证明",
        "直接证明与间接证明",
    ]


def _add_problem(
    store: TaskStore,
    *,
    question_no: int | None,
    question_type: QuestionType,
    source_hash: str | None = "source-1",
    knowledge: str = "函数",
    content_format: ContentFormat = ContentFormat.LEGACY_MARKDOWN_LATEX,
    answer: str = "",
):
    trace = {"kind": "batch_segment", "question_no": question_no}
    if source_hash:
        trace["source_file_hash"] = source_hash
    task = store.create(
        TaskCreateRequest(
            subject="math",
            metadata={"question_no": str(question_no) if question_no else None, "trace": trace},
        )
    )
    return store.set_problem(
        task.id,
        Problem(
            subject="math",
            question_type=question_type,
            content_format=content_format,
            problem_text=f"第 {question_no or '?'} 题",
            answer=answer,
            knowledge_points=[knowledge],
        ),
    )


def test_difficulty_is_ranked_inside_source_and_question_type(tmp_path):
    store = TaskStore(tmp_path / "tasks")
    choice_1 = _add_problem(store, question_no=1, question_type=QuestionType.SINGLE_CHOICE)
    choice_2 = _add_problem(store, question_no=2, question_type=QuestionType.SINGLE_CHOICE)
    fill_3 = _add_problem(store, question_no=3, question_type=QuestionType.FILL_BLANK)
    fill_4 = _add_problem(store, question_no=4, question_type=QuestionType.FILL_BLANK)
    unknown = _add_problem(
        store,
        question_no=None,
        question_type=QuestionType.SHORT_ANSWER,
        source_hash=None,
    )

    coefficients = infer_difficulty_coefficients(store.list_all())

    assert coefficients[choice_1.id] == 0.5
    assert coefficients[choice_2.id] == 1.0
    assert coefficients[fill_3.id] == 0.5
    assert coefficients[fill_4.id] == 1.0
    assert unknown.id not in coefficients


def test_auto_selection_does_not_fill_from_another_difficulty_band(tmp_path):
    store = TaskStore(tmp_path / "tasks")
    for question_no in range(1, 5):
        _add_problem(
            store,
            question_no=question_no,
            question_type=QuestionType.SINGLE_CHOICE,
        )
    payload = PaperDraftCreateRequest(
        subject="math",
        knowledge_tags=["函数"],
        difficulty_preset="easy",
        difficulty_distribution={"easy": 100, "medium": 0, "hard": 0},
        requested_counts={"单选题": 3},
    )

    items = select_paper_items(store.list_all(), payload)

    assert len(items) == 2
    assert [item.difficulty_coefficient for item in items] == [0.25, 0.5]


def test_paper_draft_api_persists_updates_and_deletes(tmp_path, monkeypatch):
    storage = tmp_path / "storage"
    task_store = TaskStore(storage)
    paper_store = PaperDraftStore(storage / "papers")
    monkeypatch.setattr(main, "TASK_STORE", task_store)
    monkeypatch.setattr(main, "PAPER_DRAFT_STORE", paper_store)
    for question_no in range(1, 5):
        _add_problem(
            task_store,
            question_no=question_no,
            question_type=QuestionType.SINGLE_CHOICE,
        )
    client = TestClient(main.app)

    created = client.post(
        "/papers",
        json={
            "title": "函数练习",
            "subject": "math",
            "knowledge_tags": ["函数"],
            "difficulty_preset": "easy",
            "difficulty_distribution": {"easy": 100, "medium": 0, "hard": 0},
            "requested_counts": {"单选题": 2},
            "auto_select": True,
        },
    )

    assert created.status_code == 201
    paper = created.json()["paper"]
    assert paper["title"] == "函数练习"
    assert len(paper["items"]) == 2
    assert paper["items"][0]["problem"]["problem_text"]

    updated = client.patch(f"/papers/{paper['id']}", json={"title": "函数专题"})
    assert updated.status_code == 200
    assert PaperDraftStore(storage / "papers").get(paper["id"]).title == "函数专题"
    assert client.get(f"/papers/{paper['id']}").json()["paper"]["title"] == "函数专题"

    deleted = client.delete(f"/papers/{paper['id']}")
    assert deleted.status_code == 200
    assert client.get(f"/papers/{paper['id']}").status_code == 404


def test_build_paper_tex_uses_oopsmark_export_and_escapes_heading():
    problem = Problem(
        subject="math",
        question_type=QuestionType.SINGLE_CHOICE,
        content_format=ContentFormat.OOPSMARK_V1,
        problem_text="求 $x^2$，并计算 $\\frac{1}{2}$。",
        options=["$x$", "$x^2$"],
        answer="B",
        explanation="因为 $x \\cdot x=x^2$。",
    )

    task = TaskRecord(id="task-1", subject="math", problem=problem)
    draft = PaperDraft(
        id="paper-1",
        title="函数_练习",
        subject="math",
        items=[
            PaperDraftItem(
                id="item-1",
                task_id=task.id,
                problem_id=problem.id,
                question_type=QuestionType.SINGLE_CHOICE.value,
                points=5,
                answer_space="large",
            )
        ],
    )
    document = build_paper_document(
        draft,
        {task.id: task},
        subtitle="第一组 & 第二组",
        show_answers=True,
    )
    tex = build_paper_tex(document)

    assert r"函数\_练习" in tex
    assert r"第一组 \& 第二组" in tex
    assert r"\frac{1}{2}" in tex
    assert r"\textbf{答案：}B" in tex
    assert r"\large\bfseries 一、单选题" in tex
    assert r"\textbf{（5分）}" in tex
    assert "\\begin{enumerate}\n\\renewcommand" in tex
    assert r"\vspace*{65mm}" not in tex


def test_paper_document_preserves_draft_order_sections_and_answer_space():
    first = Problem(
        id="problem-1",
        subject="math",
        question_type=QuestionType.SHORT_ANSWER,
        content_format=ContentFormat.OOPSMARK_V1,
        problem_text="第一题",
    )
    second = Problem(
        id="problem-2",
        subject="math",
        question_type=QuestionType.SINGLE_CHOICE,
        content_format=ContentFormat.OOPSMARK_V1,
        problem_text="第二题",
    )
    tasks = {
        "task-1": TaskRecord(id="task-1", problem=first),
        "task-2": TaskRecord(id="task-2", problem=second),
    }
    draft = PaperDraft(
        id="draft-1",
        items=[
            PaperDraftItem(
                id="item-2",
                task_id="task-2",
                problem_id="problem-2",
                question_type="单选题",
                answer_space="compact",
            ),
            PaperDraftItem(
                id="item-1",
                task_id="task-1",
                problem_id="problem-1",
                question_type="解答题",
                answer_space="large",
            ),
        ],
    )

    document = build_paper_document(draft, tasks)
    tex = build_paper_tex(document)

    assert [item.problem.id for item in document.items] == ["problem-2", "problem-1"]
    assert [section.question_type for section in document.sections] == ["单选题", "解答题"]
    assert tex.index("第二题") < tex.index("第一题")
    assert r"\vspace*{12mm}" in tex
    assert r"\vspace*{65mm}" in tex


def test_paper_bundle_copies_managed_diagram_as_content_addressed_asset(tmp_path):
    image = tmp_path / "figure.png"
    image.write_bytes(b"not-a-real-png-but-bundle-does-not-reinterpret-assets")
    problem = Problem(
        id="problem-1",
        content_format=ContentFormat.OOPSMARK_V1,
        problem_text="带图题",
    )
    task = TaskRecord(
        id="task-1",
        problem=problem,
        metadata={
            "diagram_detected": True,
            "diagram_kind": "image",
            "diagram_image_path": "/assets/figure.png",
            "diagram_position": "left",
            "diagram_scale_percent": 80,
        },
    )
    draft = PaperDraft(
        items=[
            PaperDraftItem(
                task_id=task.id,
                problem_id=problem.id,
                question_type="解答题",
            )
        ]
    )
    document = build_paper_document(draft, {task.id: task})

    bundle = build_paper_bundle(
        document,
        asset_path_resolver=lambda logical: image if logical == "/assets/figure.png" else tmp_path / "missing",
    )

    assert len(bundle.files) == 1
    assert bundle.files[0].path.startswith("assets/")
    assert bundle.files[0].content == image.read_bytes()
    assert bundle.files[0].path in bundle.tex
    assert bundle.tex.index(r"\begin{minipage}[t]{0.30\linewidth}") < bundle.tex.index("带图题")


def test_paper_document_surfaces_stale_reference_before_compilation():
    draft = PaperDraft(
        items=[
            PaperDraftItem(
                id="stale-item",
                task_id="missing-task",
                problem_id="missing-problem",
                question_type="解答题",
            )
        ]
    )

    with pytest.raises(PaperDocumentError) as error:
        build_paper_document(draft, {})

    assert error.value.code == "missing-task"
    assert error.value.item_id == "stale-item"


def test_compile_classifies_missing_engine_without_retry(monkeypatch):
    problem = Problem(
        content_format=ContentFormat.OOPSMARK_V1,
        problem_text="可导出的题目",
    )
    task = TaskRecord(id="task-1", problem=problem)
    draft = PaperDraft(
        items=[PaperDraftItem(task_id=task.id, problem_id=problem.id, question_type="解答题")]
    )
    document = build_paper_document(draft, {task.id: task})
    monkeypatch.setattr("oopsnote.paper.compiler.shutil.which", lambda _name: None)

    with pytest.raises(PaperCompileError) as error:
        compile_paper_pdf(document)

    assert error.value.code == PaperCompileFailure.MISSING_ENGINE


def test_compile_runs_two_bounded_passes_for_page_references(monkeypatch):
    problem = Problem(
        content_format=ContentFormat.OOPSMARK_V1,
        problem_text="需要总页数的题目",
    )
    task = TaskRecord(id="task-1", problem=problem)
    draft = PaperDraft(
        items=[PaperDraftItem(task_id=task.id, problem_id=problem.id, question_type="解答题")]
    )
    document = build_paper_document(draft, {task.id: task})
    calls = []

    def fake_run(command, *, cwd, **_kwargs):
        calls.append(command)
        (cwd / "paper.pdf").write_bytes(b"%PDF-1.7\n")
        return type("Result", (), {"returncode": 0, "stdout": "ok", "stderr": ""})()

    monkeypatch.setattr("oopsnote.paper.compiler.subprocess.run", fake_run)

    pdf = compile_paper_pdf(document, xelatex="test-xelatex")

    assert pdf == b"%PDF-1.7\n"
    assert len(calls) == 2
    assert all("-no-shell-escape" in command for command in calls)


def test_compile_paper_api_returns_pdf_and_unicode_filename(tmp_path, monkeypatch):
    from oopsnote.api.routes import papers as paper_routes

    task_store = TaskStore(tmp_path / "tasks")
    task = _add_problem(
        task_store,
        question_no=1,
        question_type=QuestionType.SINGLE_CHOICE,
        content_format=ContentFormat.OOPSMARK_V1,
        answer="A",
    )
    monkeypatch.setattr(main, "TASK_STORE", task_store)
    observed = {}

    def fake_compile(document, **kwargs):
        observed["document"] = document
        observed.update(kwargs)
        return b"%PDF-1.7\n"

    monkeypatch.setattr(paper_routes, "compile_paper_pdf", fake_compile)
    response = TestClient(main.app).post(
        "/papers/compile",
        json={
            "items": [{"task_id": task.id, "problem_id": task.problem.id}],
            "title": "函数练习",
            "subtitle": "第一组",
            "show_answers": True,
        },
    )

    assert response.status_code == 200
    assert response.content == b"%PDF-1.7\n"
    assert response.headers["content-type"] == "application/pdf"
    assert "filename*=UTF-8''" in response.headers["content-disposition"]
    assert observed["document"].subtitle == "第一组"
    assert observed["document"].show_answers is True
    assert observed["document"].items[0].problem.id == task.problem.id
    assert callable(observed["asset_path_resolver"])


def test_formal_draft_compile_uses_persisted_layout_properties(tmp_path, monkeypatch):
    from oopsnote.api.routes import papers as paper_routes

    storage = tmp_path / "storage"
    task_store = TaskStore(storage)
    task = _add_problem(
        task_store,
        question_no=1,
        question_type=QuestionType.SHORT_ANSWER,
        content_format=ContentFormat.OOPSMARK_V1,
    )
    paper_store = PaperDraftStore(storage / "papers")
    draft = paper_store.create(
        PaperDraftCreateRequest(title="正式试卷", subject="math", auto_select=False),
        items=[
            PaperDraftItem(
                task_id=task.id,
                problem_id=task.problem.id,
                question_type="解答题",
                points=12,
                answer_space="large",
            )
        ],
    )
    monkeypatch.setattr(main, "TASK_STORE", task_store)
    monkeypatch.setattr(main, "PAPER_DRAFT_STORE", paper_store)
    observed = {}

    def fake_compile(document, **kwargs):
        observed["document"] = document
        return b"%PDF-1.7\n"

    monkeypatch.setattr(paper_routes, "compile_paper_pdf", fake_compile)
    response = TestClient(main.app).post(
        f"/papers/{draft.id}/compile",
        json={"subtitle": "期中", "show_answers": False},
    )

    assert response.status_code == 200
    item = observed["document"].items[0]
    assert observed["document"].title == "正式试卷"
    assert observed["document"].subtitle == "期中"
    assert item.points == 12
    assert item.answer_space == "large"


def test_formal_draft_compile_reports_stale_item_as_conflict(tmp_path, monkeypatch):
    paper_store = PaperDraftStore(tmp_path / "papers")
    draft = paper_store.create(
        PaperDraftCreateRequest(title="失效试卷", auto_select=False),
        items=[
            PaperDraftItem(
                id="stale-item",
                task_id="missing-task",
                problem_id="missing-problem",
                question_type="解答题",
            )
        ],
    )
    monkeypatch.setattr(main, "TASK_STORE", TaskStore(tmp_path / "tasks"))
    monkeypatch.setattr(main, "PAPER_DRAFT_STORE", paper_store)

    response = TestClient(main.app).post(f"/papers/{draft.id}/compile", json={})

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "missing-task",
        "message": "Paper item stale-item references missing task missing-task",
        "item_id": "stale-item",
    }
