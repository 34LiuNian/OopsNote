from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from oopsnote.ai.diagram_renderer import TikzRenderBundle, TikzRenderClient, TikzRenderError
from oopsnote.api import main
from oopsnote.api.routes.papers import _expanded_knowledge_tags
from oopsnote.core import (
    AssetStore,
    ContentFormat,
    DiagramCandidate,
    DiagramItem,
    DiagramStatus,
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
    difficulty_review_reason,
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
    section_question_count: int | None = None,
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
            section_question_count=section_question_count,
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


def test_difficulty_uses_explicit_section_question_count(tmp_path):
    store = TaskStore(tmp_path / "tasks")
    choice_1 = _add_problem(
        store, question_no=1, question_type=QuestionType.SINGLE_CHOICE, section_question_count=2
    )
    choice_2 = _add_problem(
        store, question_no=2, question_type=QuestionType.SINGLE_CHOICE, section_question_count=2
    )
    fill_3 = _add_problem(
        store, question_no=3, question_type=QuestionType.FILL_BLANK, section_question_count=4
    )
    fill_4 = _add_problem(
        store, question_no=4, question_type=QuestionType.FILL_BLANK, section_question_count=4
    )
    unknown = _add_problem(
        store,
        question_no=None,
        question_type=QuestionType.SHORT_ANSWER,
        source_hash=None,
    )

    coefficients = infer_difficulty_coefficients(store.list_all())

    assert coefficients[choice_1.id] == 0.5
    assert coefficients[choice_2.id] == 1.0
    assert coefficients[fill_3.id] == 0.75
    assert coefficients[fill_4.id] == 1.0
    assert unknown.id not in coefficients


def test_difficulty_does_not_guess_section_size_from_partial_import(tmp_path):
    store = TaskStore(tmp_path / "tasks")
    imported = _add_problem(
        store,
        question_no=5,
        question_type=QuestionType.SINGLE_CHOICE,
        section_question_count=8,
    )
    missing_total = _add_problem(
        store,
        question_no=1,
        question_type=QuestionType.FILL_BLANK,
    )
    invalid_total = _add_problem(
        store,
        question_no=5,
        question_type=QuestionType.SHORT_ANSWER,
        section_question_count=4,
    )

    coefficients = infer_difficulty_coefficients(store.list_all())

    assert coefficients[imported.id] == 0.625
    assert missing_total.id not in coefficients
    assert invalid_total.id not in coefficients
    assert difficulty_review_reason(store.get(missing_total.id)) == "missing_section_question_count"
    assert (
        difficulty_review_reason(store.get(invalid_total.id))
        == "question_no_exceeds_section_question_count"
    )
    assert difficulty_review_reason(store.get(imported.id)) is None


def test_manual_difficulty_override_is_authoritative_and_can_be_cleared(tmp_path):
    store = TaskStore(tmp_path / "tasks")
    overridden = _add_problem(
        store,
        question_no=None,
        question_type=QuestionType.SHORT_ANSWER,
        source_hash=None,
    )
    ranked = _add_problem(
        store,
        question_no=1,
        question_type=QuestionType.SINGLE_CHOICE,
        section_question_count=1,
    )

    store.update(overridden.id, difficulty_coefficient_override=0.73)
    coefficients = infer_difficulty_coefficients(store.list_all())

    assert coefficients[overridden.id] == 0.73
    assert coefficients[ranked.id] == 1.0

    store.update(overridden.id, difficulty_coefficient_override=None)
    assert overridden.id not in infer_difficulty_coefficients(store.list_all())


def test_auto_selection_does_not_fill_from_another_difficulty_band(tmp_path):
    store = TaskStore(tmp_path / "tasks")
    for question_no in range(1, 5):
        _add_problem(
            store,
            question_no=question_no,
            question_type=QuestionType.SINGLE_CHOICE,
            section_question_count=4,
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
            section_question_count=4,
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
    assert r"\vspace*{12mm}" not in tex
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
        diagram_items=[
            DiagramItem(
                fallback_image_path="/assets/figure.png",
                placement={"kind": "side", "side": "left"},
                scale_adjustment_percent=80,
                status=DiagramStatus.READY_IMAGE,
            )
        ],
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
        asset_path_resolver=lambda logical: (
            image if logical == "/assets/figure.png" else tmp_path / "missing"
        ),
    )

    assert len(bundle.files) == 1
    assert bundle.files[0].path.startswith("assets/")
    assert bundle.files[0].content == image.read_bytes()
    assert bundle.files[0].path in bundle.tex
    assert bundle.tex.index(r"\begin{minipage}[t]{0.144\linewidth}") < bundle.tex.index("带图题")


def test_paper_uses_selected_same_source_pdf_instead_of_recompiling_tikz(tmp_path):
    pdf = tmp_path / "diagram.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    problem = Problem(
        id="problem-tikz",
        content_format=ContentFormat.OOPSMARK_V1,
        problem_text="TikZ 图题",
        has_diagram=True,
    )
    candidate = DiagramCandidate(
        ordinal=1,
        tikz_source="\\draw (0,0)--(1,0);",
        svg_path="/assets/diagram.svg",
        pdf_path="/assets/diagram.pdf",
        png_path="/assets/diagram.png",
        base_font_size_pt=10,
        canvas_width_em=12,
        canvas_height_em=8,
        decision="accept",
    )
    task = TaskRecord(
        id="task-tikz",
        problem=problem,
        diagram_items=[
            DiagramItem(
                status=DiagramStatus.READY_TIKZ,
                selected_candidate_id=candidate.id,
                candidates=[candidate],
            )
        ],
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

    bundle = build_paper_bundle(
        build_paper_document(draft, {task.id: task}),
        asset_path_resolver=lambda logical: (
            pdf if logical == "/assets/diagram.pdf" else tmp_path / "missing"
        ),
    )

    assert len(bundle.files) == 1
    assert bundle.files[0].content == pdf.read_bytes()
    assert candidate.tikz_source not in bundle.tex
    assert r"\includegraphics" in bundle.tex
    assert r"\includegraphics[width=7.2em,keepaspectratio]" in bundle.tex


def test_hidden_diagram_is_absent_from_paper_projection():
    problem = Problem(
        id="problem-hidden-diagram",
        content_format=ContentFormat.OOPSMARK_V1,
        problem_text="隐藏附图",
        has_diagram=True,
    )
    task = TaskRecord(
        id="task-hidden-diagram",
        problem=problem,
        diagram_items=[
            DiagramItem(
                enabled=False,
                fallback_image_path="/assets/hidden.png",
                status=DiagramStatus.READY_IMAGE,
            )
        ],
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

    assert document.items[0].diagram is None


def test_paper_ignores_legacy_diagram_flag_without_reconstructed_item():
    problem = Problem(
        id="problem-legacy-flag",
        content_format=ContentFormat.OOPSMARK_V1,
        problem_text="历史记录仅保留了图形标记",
        has_diagram=True,
    )
    task = TaskRecord(id="task-legacy-flag", problem=problem)
    draft = PaperDraft(
        items=[
            PaperDraftItem(
                task_id=task.id,
                problem_id=problem.id,
                question_type="单选题",
            )
        ]
    )

    document = build_paper_document(draft, {task.id: task})

    assert document.items[0].diagram is None


def test_paper_rejects_legacy_tikz_without_normalized_size_metrics():
    problem = Problem(
        id="problem-legacy-diagram",
        content_format=ContentFormat.OOPSMARK_V1,
        problem_text="旧附图",
        has_diagram=True,
    )
    candidate = DiagramCandidate(
        ordinal=1,
        tikz_source=r"\draw (0,0)--(1,0);",
        pdf_path="/assets/legacy.pdf",
    )
    task = TaskRecord(
        id="task-legacy-diagram",
        problem=problem,
        diagram_items=[
            DiagramItem(
                status=DiagramStatus.READY_TIKZ,
                selected_candidate_id=candidate.id,
                candidates=[candidate],
            )
        ],
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

    with pytest.raises(PaperDocumentError) as caught:
        build_paper_document(draft, {task.id: task})

    assert caught.value.code == "diagram-size-metrics-missing"


def test_wide_side_tikz_deterministically_falls_back_after_options(tmp_path):
    pdf = tmp_path / "wide.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    problem = Problem(
        id="problem-wide-diagram",
        content_format=ContentFormat.OOPSMARK_V1,
        problem_text="宽图题",
        options=["选项"],
        has_diagram=True,
    )
    candidate = DiagramCandidate(
        ordinal=1,
        tikz_source=r"\draw (0,0)--(1,0);",
        pdf_path="/assets/wide.pdf",
        base_font_size_pt=10,
        canvas_width_em=15,
        canvas_height_em=8,
    )
    task = TaskRecord(
        id="task-wide-diagram",
        problem=problem,
        diagram_items=[
            DiagramItem(
                status=DiagramStatus.READY_TIKZ,
                selected_candidate_id=candidate.id,
                candidates=[candidate],
            )
        ],
    )
    draft = PaperDraft(
        items=[
            PaperDraftItem(
                task_id=task.id,
                problem_id=problem.id,
                question_type="单选题",
            )
        ]
    )

    # The default 60% export scale leaves this diagram in the side slot.  Use
    # the explicit legacy-sized export scale to exercise the deterministic
    # wide-side fallback itself.
    bundle = build_paper_bundle(
        build_paper_document(draft, {task.id: task}, diagram_scale_percent=100),
        asset_path_resolver=lambda _logical: pdf,
    )

    assert bundle.tex.index(r"\end{enumerate}") < bundle.tex.index(r"\includegraphics[width=15em")
    assert r"\makebox[\linewidth][r]" in bundle.tex


def test_four_options_emit_latex_width_adaptive_layout():
    problem = Problem(
        id="problem-options",
        content_format=ContentFormat.OOPSMARK_V1,
        problem_text="选项布局",
        options=["1", "这是一个中等长度的选项", "$x^2+1$", "最后一个选项"],
    )
    task = TaskRecord(id="task-options", problem=problem)
    draft = PaperDraft(
        items=[
            PaperDraftItem(
                task_id=task.id,
                problem_id=problem.id,
                question_type="单选题",
            )
        ]
    )

    tex = build_paper_tex(build_paper_document(draft, {task.id: task}))

    assert r"\setbox0=\hbox{A.\enspace" in tex
    assert r"\ifdim\dimen0<0.24\linewidth" in tex
    assert r"\makebox[0.25\linewidth][l]{\copy0}" in tex
    assert r"\else\ifdim\dimen0<0.49\linewidth" in tex
    assert r"\makebox[0.5\linewidth][l]{\copy0}" in tex
    assert "\\else\n\\noindent\\copy0\\par" in tex
    assert r"\copy0\par" in tex
    assert r"}%\makebox" not in tex


def test_diagram_scale_adjustment_and_paper_scale_are_applied_once(tmp_path):
    pdf = tmp_path / "diagram.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    problem = Problem(
        id="problem-scaled-diagram",
        content_format=ContentFormat.OOPSMARK_V1,
        problem_text="缩放题图",
        has_diagram=True,
    )
    candidate = DiagramCandidate(
        ordinal=1,
        tikz_source=r"\draw (0,0)--(1,0);",
        pdf_path="/assets/diagram.pdf",
        base_font_size_pt=10,
        canvas_width_em=10,
        canvas_height_em=5,
    )
    task = TaskRecord(
        id="task-scaled-diagram",
        problem=problem,
        diagram_items=[
            DiagramItem(
                status=DiagramStatus.READY_TIKZ,
                selected_candidate_id=candidate.id,
                candidates=[candidate],
                scale_adjustment_percent=80,
            )
        ],
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

    document = build_paper_document(draft, {task.id: task}, diagram_scale_percent=75)
    tex = build_paper_bundle(
        document,
        asset_path_resolver=lambda _logical: pdf,
    ).tex

    assert r"\includegraphics[width=6em,keepaspectratio]" in tex
    assert r"width=4.8em" not in tex


def test_non_answer_questions_ignore_answer_space_setting():
    problem = Problem(
        id="problem-choice-space",
        content_format=ContentFormat.OOPSMARK_V1,
        problem_text="选择题不留解答空间",
    )
    task = TaskRecord(id="task-choice-space", problem=problem)
    draft = PaperDraft(
        items=[
            PaperDraftItem(
                task_id=task.id,
                problem_id=problem.id,
                question_type="单选题",
                answer_space="large",
            )
        ]
    )

    tex = build_paper_tex(build_paper_document(draft, {task.id: task}))

    assert r"\vspace*{35mm}" not in tex
    assert r"\vspace*{65mm}" not in tex


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
            "diagram_scale_percent": 75,
        },
    )

    assert response.status_code == 200
    assert response.content == b"%PDF-1.7\n"
    assert response.headers["content-type"] == "application/pdf"
    assert "filename*=UTF-8''" in response.headers["content-disposition"]
    assert observed["document"].subtitle == "第一组"
    assert observed["document"].show_answers is True
    assert observed["document"].diagram_scale_percent == 75
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
        json={"subtitle": "期中", "show_answers": False, "diagram_scale_percent": 75},
    )

    assert response.status_code == 200
    item = observed["document"].items[0]
    assert observed["document"].title == "正式试卷"
    assert observed["document"].subtitle == "期中"
    assert observed["document"].diagram_scale_percent == 75
    assert item.points == 12
    assert item.answer_space == "large"


def test_formal_draft_compile_upgrades_legacy_tikz_once(tmp_path, monkeypatch):
    from oopsnote.api.routes import papers as paper_routes

    storage = tmp_path / "storage"
    task_store = TaskStore(storage / "tasks")
    asset_store = AssetStore(storage / "assets")
    task = _add_problem(
        task_store,
        question_no=1,
        question_type=QuestionType.SHORT_ANSWER,
        content_format=ContentFormat.OOPSMARK_V1,
    )
    candidate = DiagramCandidate(
        ordinal=1,
        tikz_source=r"\begin{tikzpicture}\draw (0,0)--(1,0);\end{tikzpicture}",
        svg_path="/assets/legacy.svg",
        pdf_path="/assets/legacy.pdf",
        png_path="/assets/legacy.png",
        renderer_profile_version="tikz-xelatex-v2-poppler",
    )
    diagram = DiagramItem(
        status=DiagramStatus.READY_TIKZ,
        selected_candidate_id=candidate.id,
        candidates=[candidate],
    )
    task_store.add_diagram_item(task.id, diagram)
    paper_store = PaperDraftStore(storage / "papers")
    draft = paper_store.create(
        PaperDraftCreateRequest(title="旧题图试卷", subject="math", auto_select=False),
        items=[
            PaperDraftItem(
                task_id=task.id,
                problem_id=task.problem.id,
                question_type="解答题",
            )
        ],
    )
    monkeypatch.setattr(main, "TASK_STORE", task_store)
    monkeypatch.setattr(main, "ASSET_STORE", asset_store)
    monkeypatch.setattr(main, "PAPER_DRAFT_STORE", paper_store)
    render_calls = 0

    def render_bundle(renderer: TikzRenderClient, source: str) -> TikzRenderBundle:
        nonlocal render_calls
        render_calls += 1
        assert source == candidate.tikz_source
        return TikzRenderBundle(
            svg_path=renderer.asset_store.save_bytes(b"<svg/>", "diagram.svg", "paper-upgrade"),
            pdf_path=renderer.asset_store.save_bytes(b"pdf", "diagram.pdf", "paper-upgrade"),
            png_path=renderer.asset_store.save_bytes(b"png", "diagram.png", "paper-upgrade"),
            renderer_profile_version="tikz-xelatex-v6-test",
            base_font_size_pt=10,
            canvas_width_em=12.5,
            canvas_height_em=7.25,
        )

    monkeypatch.setattr(TikzRenderClient, "render", render_bundle)
    monkeypatch.setattr(paper_routes, "compile_paper_pdf", lambda *_args, **_kwargs: b"pdf")
    client = TestClient(main.app)

    first = client.post(f"/papers/{draft.id}/compile", json={})
    second = client.post(f"/papers/{draft.id}/compile", json={})

    assert first.status_code == 200
    assert second.status_code == 200
    assert render_calls == 1
    selected = task_store.get(task.id).diagram_items[0].candidates[0]
    assert selected.id == candidate.id
    assert selected.tikz_source == candidate.tikz_source
    assert selected.renderer_profile_version == "tikz-xelatex-v6-test"
    assert selected.base_font_size_pt == 10
    assert selected.canvas_width_em == 12.5
    assert selected.canvas_height_em == 7.25


def test_formal_draft_compile_preserves_legacy_candidate_when_upgrade_fails(
    tmp_path,
    monkeypatch,
):
    from oopsnote.api.routes import papers as paper_routes

    storage = tmp_path / "storage"
    task_store = TaskStore(storage / "tasks")
    asset_store = AssetStore(storage / "assets")
    task = _add_problem(
        task_store,
        question_no=1,
        question_type=QuestionType.SHORT_ANSWER,
        content_format=ContentFormat.OOPSMARK_V1,
    )
    candidate = DiagramCandidate(
        ordinal=1,
        tikz_source=r"\draw (0,0)--(1,0);",
        pdf_path="/assets/legacy.pdf",
        renderer_profile_version="tikz-xelatex-v2-poppler",
    )
    diagram = DiagramItem(
        status=DiagramStatus.READY_TIKZ,
        selected_candidate_id=candidate.id,
        candidates=[candidate],
    )
    task_store.add_diagram_item(task.id, diagram)
    paper_store = PaperDraftStore(storage / "papers")
    draft = paper_store.create(
        PaperDraftCreateRequest(title="失败升级", subject="math", auto_select=False),
        items=[
            PaperDraftItem(
                id="draft-item",
                task_id=task.id,
                problem_id=task.problem.id,
                question_type="解答题",
            )
        ],
    )
    monkeypatch.setattr(main, "TASK_STORE", task_store)
    monkeypatch.setattr(main, "ASSET_STORE", asset_store)
    monkeypatch.setattr(main, "PAPER_DRAFT_STORE", paper_store)

    def fail_render(_renderer: TikzRenderClient, _source: str) -> TikzRenderBundle:
        raise TikzRenderError("renderer_timeout", "TikZ rendering timed out", retryable=True)

    def must_not_compile(*_args, **_kwargs):
        pytest.fail("paper compiler ran after the TikZ upgrade failed")

    monkeypatch.setattr(TikzRenderClient, "render", fail_render)
    monkeypatch.setattr(paper_routes, "compile_paper_pdf", must_not_compile)

    response = TestClient(main.app).post(f"/papers/{draft.id}/compile", json={})

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "category": "tikz_compile",
        "code": "renderer_timeout",
        "message": "TikZ rendering timed out",
        "retryable": True,
        "scope": "paper_compile",
        "task_id": task.id,
        "diagram_item_id": diagram.id,
        "details": {"item_id": "draft-item", "problem_id": task.problem.id},
    }
    persisted = task_store.get(task.id).diagram_items[0].candidates[0]
    assert persisted.model_dump() == candidate.model_dump()


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
        "category": "request",
        "code": "missing_task",
        "message": "Paper item stale-item references missing task missing-task",
        "retryable": False,
        "scope": "paper_compile",
        "details": {"item_id": "stale-item"},
    }
