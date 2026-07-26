from __future__ import annotations

from fastapi.testclient import TestClient

from oopsnote.api import main
from oopsnote.api.routes.papers import _expanded_knowledge_tags
from oopsnote.core import (
    ContentFormat,
    PaperDraftCreateRequest,
    PaperDraftStore,
    Problem,
    QuestionType,
    TaskCreateRequest,
    TaskStore,
)
from oopsnote.paper import infer_difficulty_coefficients, select_paper_items
from oopsnote.paper import build_paper_tex


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
            problem_text=f"第 {question_no or '?'} 题",
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

    tex = build_paper_tex(
        [problem],
        title="函数_练习",
        subtitle="第一组 & 第二组",
        show_answers=True,
    )

    assert r"函数\_练习" in tex
    assert r"第一组 \& 第二组" in tex
    assert r"\frac{1}{2}" in tex
    assert r"\textbf{答案：}B" in tex
    assert "\\begin{enumerate}\n\\renewcommand" in tex


def test_compile_paper_api_returns_pdf_and_unicode_filename(tmp_path, monkeypatch):
    from oopsnote.api.routes import papers as paper_routes

    task_store = TaskStore(tmp_path / "tasks")
    task = _add_problem(
        task_store,
        question_no=1,
        question_type=QuestionType.SINGLE_CHOICE,
    )
    monkeypatch.setattr(main, "TASK_STORE", task_store)
    observed = {}

    def fake_compile(problems, **kwargs):
        observed["problems"] = problems
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
    assert observed["subtitle"] == "第一组"
    assert observed["show_answers"] is True
