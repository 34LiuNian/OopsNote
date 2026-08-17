from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException


def _load_renderer_module():
    path = Path(__file__).parents[1] / "deploy" / "latex-renderer" / "app.py"
    spec = importlib.util.spec_from_file_location("oopsnote_latex_renderer", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_tikz_outputs_generate_svg_from_pdf_and_keep_png(tmp_path, monkeypatch):
    renderer = _load_renderer_module()
    xdv = tmp_path / "diagram.xdv"
    xdv.write_bytes(b"xdv")
    commands: list[list[str]] = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        if command[0] == "xdvipdfmx":
            (tmp_path / "diagram.pdf").write_bytes(b"pdf")
        elif "-svg" in command:
            (tmp_path / "diagram.svg").write_text(
                "<svg><defs><path d='glyph'/></defs><path d='shape'/></svg>",
                encoding="utf-8",
            )
        else:
            (tmp_path / "diagram.png").write_bytes(b"png")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(renderer, "_svg_converter", lambda: "pdftocairo")
    monkeypatch.setattr(renderer, "_png_converter", lambda: ("poppler", "pdftocairo"))
    monkeypatch.setattr(renderer.subprocess, "run", fake_run)

    svg, pdf, png = renderer._convert_tikz_outputs(tmp_path, xdv)

    assert svg.name == "diagram.svg"
    assert pdf.name == "diagram.pdf"
    assert png.name == "diagram.png"
    assert commands[1] == ["pdftocairo", "-svg", "diagram.pdf", "diagram.svg"]


def test_tikz_outputs_reject_svg_without_drawable_body(tmp_path, monkeypatch):
    renderer = _load_renderer_module()
    xdv = tmp_path / "diagram.xdv"
    xdv.write_bytes(b"xdv")

    def fake_run(command, **_kwargs):
        if command[0] == "xdvipdfmx":
            (tmp_path / "diagram.pdf").write_bytes(b"pdf")
        elif "-svg" in command:
            (tmp_path / "diagram.svg").write_text(
                "<svg><defs><path d='glyph'/></defs><g><use href='#glyph'/></g></svg>",
                encoding="utf-8",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(renderer, "_svg_converter", lambda: "pdftocairo")
    monkeypatch.setattr(renderer, "_png_converter", lambda: ("poppler", "pdftocairo"))
    monkeypatch.setattr(renderer.subprocess, "run", fake_run)

    with pytest.raises(HTTPException, match="no drawable paths"):
        renderer._convert_tikz_outputs(tmp_path, xdv)


def test_pdf_canvas_is_normalized_by_explicit_tikz_default_font(tmp_path, monkeypatch):
    renderer = _load_renderer_module()
    pdf = tmp_path / "diagram.pdf"
    pdf.write_bytes(b"pdf")

    monkeypatch.setattr(
        renderer.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout="MediaBox: 0.00 0.00 144.00 72.00\n",
            stderr="",
        ),
    )

    width_em, height_em = renderer._pdf_canvas_em(pdf)

    base_font_pdf_pt = 10 * 72 / 72.27
    assert width_em == pytest.approx(144 / base_font_pdf_pt)
    assert height_em == pytest.approx(72 / base_font_pdf_pt)


def test_pdf_canvas_rejects_missing_media_box(tmp_path, monkeypatch):
    renderer = _load_renderer_module()
    pdf = tmp_path / "diagram.pdf"
    pdf.write_bytes(b"pdf")
    monkeypatch.setattr(
        renderer.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout="Page size: 144 x 72 pts\n",
            stderr="",
        ),
    )

    with pytest.raises(HTTPException, match="readable MediaBox"):
        renderer._pdf_canvas_em(pdf)


def test_legacy_svg_canvas_dimensions_are_migrated_without_label_inspection():
    from oopsnote.ai.diagram_renderer import legacy_svg_canvas_em

    metrics = legacy_svg_canvas_em(
        '<svg xmlns="http://www.w3.org/2000/svg" width="329.48pt" height="156.73pt" />'
    )

    assert metrics is not None
    base_font_pdf_pt = 10 * 72 / 72.27
    assert metrics[0] == pytest.approx(329.48 / base_font_pdf_pt)
    assert metrics[1] == pytest.approx(156.73 / base_font_pdf_pt)
    assert legacy_svg_canvas_em("<svg><text>not used</text></svg>") is None
