Provider marks in this directory are the 331 canonical (non-text) icons from
LobeHub's `@lobehub/icons-static-svg` package version 1.94.0. The package and
these assets are distributed under its MIT license.

`index.json` is generated from the imported SVG filenames and is used by the
local channel icon picker. The picker uses the `-color` variant for every
choice; when upstream has no color variant, the canonical icon is copied to a
same-name `-color.svg` fallback. The `-text` and `-brand` variants are excluded
so each choice stays a compact square mark.
