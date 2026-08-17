---
name: oopsnote-diagram-reconstruction
description: "Reconstruct and visually verify one printed problem diagram as safe body-only TikZ."
---

# Reconstruct One Problem Diagram

Reconstruct only the printed problem diagram as safe body-only TikZ. Never include handwriting, grading marks, question prose, `documentclass`, `usepackage`, or document wrappers.

Ordinary labels must inherit the renderer's default font size. Do not add font-size commands or text-node scaling merely to imitate minor source-image size differences. Use explicitly smaller or larger labels only when semantic hierarchy, readability, or collision avoidance requires it; the renderer maps the inherited default size to the final problem body size.

Respond only by calling exactly one tool currently bound by the runner. The tool name is the decision; never return a JSON decision object or prose outside a tool call. @decisions

Hard errors are: wrong, missing, or extra labels; label-object mismatch; wrong topology or connectivity; wrong arrows, directions, or magnetic dot/cross symbols; wrong incidence, order, intersection, tangency, parallel/perpendicular, or inside/outside relations; wrong axes, ticks, thresholds, extrema, intersections, or semantic line styles; wrong apparatus state, liquid level, gas path, reagent, or connection; wrong 3D occlusion; unreadable overlap or clipping; contamination by handwriting or question text; missing structures; unsafe or non-body-only source.

Accept all soft differences: small overall size, aspect, font-family, line-width, or spacing changes; curve control-point changes that preserve relations; and non-semantic shading simplification. Preserve meaningful relative label-size hierarchy when the source clearly uses one.

@fallback_policy

When a bound tool accepts `hard_errors` or `soft_differences`, pass them as arrays of concise strings. @source_region_policy
