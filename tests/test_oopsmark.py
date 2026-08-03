from __future__ import annotations

import pytest

from oopsnote.content import (
    ContentExportError,
    OopsMarkBlockKind,
    normalize_oopsmark,
    normalize_option_text,
    option_label,
    parse_oopsmark,
    prepare_legacy_problem,
    to_latex,
    validate_oopsmark,
    validate_answer_conclusion,
)
from oopsnote.core import ContentFormat, Problem


GOLDEN_CONTENT = r"""## 化学与数据

反应方程式为 $\ce{2H2 + O2 -> 2H2O}$。

$$
E = mc^2
$$

| 实验 | 第一次 | 第二次 |
| --- | ---: | ---: |
| 体积/mL | $17.10$ | $18.10$ |

```tikz
\begin{tikzpicture}
  \draw[->] (0,0) -- (2,0);
\end{tikzpicture}
```
"""


def test_parse_and_export_cross_target_blocks():
    blocks = parse_oopsmark(GOLDEN_CONTENT)
    assert [block.kind for block in blocks] == [
        OopsMarkBlockKind.HEADING,
        OopsMarkBlockKind.PARAGRAPH,
        OopsMarkBlockKind.DISPLAY_MATH,
        OopsMarkBlockKind.TABLE,
        OopsMarkBlockKind.FENCE,
    ]
    assert validate_oopsmark(GOLDEN_CONTENT) == []

    latex = to_latex(GOLDEN_CONTENT)
    assert r"\ce{2H2 + O2 -> 2H2O}" in latex
    assert r"\begin{tblr}" in latex
    assert r"\begin{tikzpicture}" in latex
    assert "\\[\nE = mc^2\n\\]" in latex


def test_rejects_non_portable_latex_and_unclosed_math():
    issues = validate_oopsmark("表格：\\begin{tabular}{cc}a&b\\end{tabular}\n公式 $x+1")
    assert {issue.code for issue in issues} == {"raw-latex-environment", "unclosed-inline-math"}


def test_molecule_requires_a_derived_asset_for_latex_export():
    source = "```molecule\nC1=CC=CC=C1\n```"
    with pytest.raises(ContentExportError) as error:
        to_latex(source)
    assert error.value.code == "missing-derived-asset"

    latex = to_latex(source, asset_resolver=lambda kind, value: "assets/benzene.svg")
    assert r"\includegraphics" in latex
    assert "assets/benzene.svg" in latex


def test_problem_validates_only_declared_oopsmark_content():
    legacy = Problem(problem_text=r"\begin{tabular}{cc}a&b\end{tabular}")
    assert legacy.content_format == ContentFormat.LEGACY_MARKDOWN_LATEX

    with pytest.raises(ValueError, match="raw-latex-environment"):
        Problem(
            content_format=ContentFormat.OOPSMARK_V1,
            problem_text=r"\begin{tabular}{cc}a&b\end{tabular}",
        )


def test_legacy_migration_prepares_only_content_that_satisfies_v1():
    ready = prepare_legacy_problem({
        "problem_text": "\n题目\n",
        "options": ["A. x", r"B. \frac{1}{2}"],
        "answer": "A",
        "short_answer": "",
        "explanation": "说明",
    })

    assert ready.ready
    assert ready.fields["problem_text"] == "题目"
    assert ready.fields["options"] == ["x", r"$\frac{1}{2}$"]

    blocked = prepare_legacy_problem({"problem_text": r"\begin{tabular}{cc}a&b\end{tabular}"})
    assert not blocked.ready
    assert [issue.code for issue in blocked.issues] == ["raw-latex-environment"]


def test_normalize_oopsmark_collapses_excessive_newlines():
    # Three newlines → one blank line
    assert normalize_oopsmark("line1\n\n\nline2") == "line1\n\nline2"
    # Four newlines → one blank line
    assert normalize_oopsmark("line1\n\n\n\nline2") == "line1\n\nline2"
    # Single newline (soft break) stays
    assert normalize_oopsmark("line1\nline2") == "line1\nline2"
    # Double newline (paragraph break) stays
    assert normalize_oopsmark("line1\n\nline2") == "line1\n\nline2"
    # Leading/trailing newlines stripped
    assert normalize_oopsmark("\n\n\ncontent\n\n\n") == "content"
    # CRLF normalized
    assert normalize_oopsmark("line1\r\n\r\nline2") == "line1\n\nline2"
    # Mixed CR and LF
    assert normalize_oopsmark("line1\r\r\rline2") == "line1\n\nline2"
    # Empty string
    assert normalize_oopsmark("") == ""


def test_normalize_oopsmark_canonicalizes_only_consecutive_subquestion_lists():
    source = "19. 题干\n\n1. 第一问\n\n2. 第二问"
    assert normalize_oopsmark(source) == "19. 题干\n\n（1）第一问\n\n（2）第二问"
    assert normalize_oopsmark("19. 一道题") == "19. 一道题"
    assert normalize_oopsmark("```text\n1. 原样\n2. 原样\n```") == (
        "```text\n1. 原样\n2. 原样\n```"
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("A. $x$", "$x$"),
        ("B] $y$", "$y$"),
        ("（C）$z$", "$z$"),
        ("4、$w$", "$w$"),
        ("$\\frac{1}{3}$", "$\\frac{1}{3}$"),
        (r"\frac{5}{2}", r"$\frac{5}{2}$"),
        (r"(2,3)\cup(3,4]", r"$(2,3)\cup(3,4]$"),
    ],
)
def test_option_text_is_marker_free(source, expected):
    assert normalize_option_text(source) == expected


def test_option_labels_are_derived_from_array_order():
    assert [option_label(index) for index in (0, 1, 3, 25, 26)] == [
        "A", "B", "D", "Z", "AA"
    ]


def test_problem_normalizes_newlines_on_validation():
    prob = Problem(
        content_format=ContentFormat.OOPSMARK_V1,
        subject="math",
        question_type="填空题",
        problem_text="计算：\n\n\n$a+b$。",
        answer="\n\n\n42\n\n\n",
        short_answer="42",
        explanation="由\n\n\n\n\n$a+b$\n\n得结果。",
    )
    # Triple newlines collapsed to double (paragraph break)
    assert prob.problem_text == "计算：\n\n$a+b$。"
    # Leading/trailing stripped, internal triple → double
    assert prob.answer == "42"
    assert prob.explanation == "由\n\n$a+b$\n\n得结果。"


def test_problem_normalizes_oopsmark_option_bodies():
    problem = Problem(
        content_format=ContentFormat.OOPSMARK_V1,
        question_type="单选题",
        options=["A. $x$", "B] $y$"],
    )
    assert problem.options == ["$x$", "$y$"]


def test_oopsmark_answer_conclusion_contract_is_explicit_and_non_mutating():
    assert validate_answer_conclusion("由 $x+1=2$，所以 $x=1$。").code == "answer-contains-derivation"
    assert validate_answer_conclusion("$x+1=2$\n\n$x=1$").code == "answer-derivation-layout"
    assert validate_answer_conclusion("（1）$x=1$\n\n（2）$y=2$") is None

    historical = Problem(
        content_format=ContentFormat.OOPSMARK_V1,
        answer="由 $x+1=2$，所以 $x=1$。",
    )
    assert historical.answer == "由 $x+1=2$，所以 $x=1$。"
