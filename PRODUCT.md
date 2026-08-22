# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary users are students who need to consolidate mistakes and worthwhile problems after regular homework, compressed term-time workloads, weekend study, holiday study, or revision. Their job is to turn scattered problem material into a reviewable knowledge system, receive useful learning feedback, and export organized questions for later study.

## Product Purpose

OopsNote is an AI-assisted, local-first personal question-management application. It helps students capture or enter questions, organize and review them, build a knowledge structure from them, and export the resulting material. Success means less manual intake and organization while preserving enough trustworthy problem context for effective review and reuse.

## Positioning

OopsNote combines image/manual question intake with OCR, solving, validation, tagging, searchable local question storage, Obsidian synchronization, and paper export in one workflow. Its differentiated promise is higher automation with less manual intervention, while retaining one canonical editable problem source instead of creating disconnected OCR, question-bank, and export copies.

## Operating Context

- Used primarily outside class, including at home, on weekends, during holidays, and in revision periods.
- Input material includes photographed questions, manually entered questions, and user-selected regions from batches of images.
- Core workflows are capture, OCR/AI processing, review and correction, tagging into a knowledge system, search and review, paper assembly, and export.
- Web is the primary interface; Obsidian is an explicit user-controlled data outlet.

## Capabilities and Constraints

- OopsMark v1 is the canonical editable content format for problem text, options, answers, and explanations. Web rendering, Obsidian output, and paper export derive from that source; they must not create a second editable representation.
- The application is local-first. User runtime data and evidence remain local under the managed storage and vault boundaries.
- The AI workflow is deliberately bounded: LangChain is the sole AI runtime, `ManagedAiRunner` owns lifecycle state, and AI capabilities are limited to image OCR and the restricted OopsNote MCP pipeline.
- Production authentication uses Better Auth; loopback-only local development remains explicit.
- The interface must preserve explicit saved, progress, failure, and recovery evidence. It must not conceal deterministic failures behind silent fallbacks or retries.
- Current reliable image workflow supports single-image intake, manual entry, and manual batch-region selection. Automatic page segmentation is not a current reliable path.

## Brand Commitments

- Product name: OopsNote.
- The product is an academic workbench, not a generic note-taking or promotional product.
- Real questions, formulas, diagrams, scans, and generated papers are core product material and must remain inspectable and exportable.

## Evidence on Hand

- Canonical content contract: `docs/oopsmark-v1.md`.
- Architecture and data-boundary evidence: `docs/ARCHITECTURE.md`.
- Existing capability and workflow evidence: `README.md` and the `frontend/` application.
- No customer testimonials, benchmark claims, or external proof assets are confirmed for future product work; do not fabricate them.

## Product Principles

1. Reduce manual intake and organization without hiding what the system did or changing the user's source material silently.
2. Treat a question, its knowledge context, and its exportable form as one coherent learning record.
3. Make review and learning feedback actionable in the student’s real study rhythm, not merely archival.
4. Preserve local control, canonical content, and explicit failure evidence across AI-assisted workflows.
5. Keep academic material usable across capture, inspection, organization, and output.

## Accessibility & Inclusion

- No product-specific accessibility standard has been confirmed yet. Existing Web work must continue to support keyboard operation, clear status/error communication, readable Chinese and mathematical content, responsive layouts, and the project design system’s coarse-pointer target requirements.
