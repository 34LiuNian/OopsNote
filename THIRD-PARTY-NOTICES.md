# Third-Party Notices

This file records third-party material that is included in, copied into, or
used as a reference by OopsNote. The root `LICENSE` applies only to original
OopsNote code and documentation unless a file says otherwise.

## License boundary

Original OopsNote code is licensed under `AGPL-3.0-or-later`. A dependency's
license is not changed by the root project license. When distributing a build,
keep the relevant copyright and license notices for the dependencies included
in that build.

## Frontend dependencies

The frontend uses packages declared in `frontend/package.json` and locked in
`frontend/package-lock.json`. Their package metadata and distributed license
files remain authoritative. Do not copy the root AGPL notice into their source
files or present them as OopsNote code.

The current lockfile records permissive licenses including MIT, Apache-2.0,
BSD, ISC, and related dual-license expressions. It also contains copyleft or
source-specific entries in the TikZ rendering chain; those are listed below.
Any package with a combined expression must retain all applicable license
choices and notices when it is redistributed.

## TikZ rendering chain

- `isomorphic-tikzjax` (`frontend/package-lock.json`): LPPL-1.3c.
- `@prinsss/dvi2html` (`frontend/package-lock.json`): GPL-3.0, as a
  transitive dependency of `isomorphic-tikzjax`.
- `frontend/public/vendor/tikzjax/worker.js`: generated/bundled renderer code
  with embedded license information.
- `frontend/public/vendor/tikzjax/css/bakoma/LICENCE`: license notice for the
  bundled Bakoma fonts.

This chain is used by `frontend/components/renderers/TikzWorker.ts` and its
assets are copied into the public build. A release containing the TikZ
renderer must ship the upstream LPPL/GPL/Bakoma notices and the corresponding
source or source-offer information required by those licenses. Do not claim
that the frontend dependency set is MIT/Apache-only.

## Sirivennela-Regular

- File: `frontend/public/fonts/Sirivennela-Regular.ttf`
- License: SIL Open Font License 1.1 (OFL-1.1)
- Project: Sirivennela-Regular

This font remains under OFL-1.1 and is not relicensed under AGPL. The font's
upstream copyright notice and the complete OFL-1.1 text must be kept with any
redistributed build. Before the first public release, verify the upstream
copyright line against the exact font distribution and add the official OFL
text to the release notices.

## MIT loading component

The loading component is treated as third-party MIT material according to its
source provenance. Preserve the original copyright notice, license text, and
source URL when redistributing it. The exact upstream project and copyright
holder are not currently recorded in this repository; publication is blocked
until that provenance is added here or in the component file.

## imsyy/home

The `imsyy/home` repository is marked MIT on its GitHub repository page. It was
used as a visual/loading-page reference. No `imsyy/home` source path or asset
was found in the current repository. If code or assets are copied later, retain
the upstream MIT notice and identify the copied paths here; visual inspiration
alone is not being treated as copied source.

## Frameworks and generated assets

React, Next.js, Mantine, KaTeX, Mermaid, PDF.js, Playwright, and other tools in
the dependency manifests keep their own licenses. Generated bundles may also
contain their notices, so a production distribution should be checked after
the build rather than assuming the source repository's `LICENSE` is enough.

This inventory is an engineering record, not legal advice. License compliance
must be rechecked whenever a dependency, bundled asset, or copied code changes.
