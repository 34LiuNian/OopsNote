# OopsNote paper template

`paper.tex` is the only authoritative document-level LaTeX template.

The paper compiler owns semantic adaptation:

1. Core `PaperDraft` and referenced `Problem` records are projected to `PaperDocument`.
2. The OopsMark adapter renders question content and registers managed assets.
3. `paper.tex` supplies document packages, page geometry, fonts, and page numbering.
4. The compiler writes one isolated bundle and runs two bounded XeLaTeX passes.

Do not add question-type rules, numbering state, answer-space mappings, or asset lookup to
the template. Those contracts belong to `PaperDocument` and the compiler adapter so local
and future remote compilers consume the same bundle.

Required TeX capabilities currently include XeLaTeX and the packages provided by `ctex`,
`amsmath`, `amssymb`, `mhchem`, `graphicx`, `tikz`, `tabularray`, `geometry`, `fancyhdr`, and
`lastpage`. The template explicitly uses the TeX-distributed Fandol CJK font set to avoid
platform-specific font selection.
