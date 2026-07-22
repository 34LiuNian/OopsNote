from __future__ import annotations

import pytest

from oopsnote.content import ContentExportError, OopsMarkBlockKind, parse_oopsmark, to_latex, validate_oopsmark
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
