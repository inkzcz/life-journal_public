# Binary distribution notice

Copyright (C) 2026 inkzcz. Owner-controlled original Life Journal code and original
increments are GPL-3.0-or-later, as scoped by COPYRIGHT.md. This is not a change to
any third-party grant. The current combination can use GPL version 3; third-party
GPL-3.0-only / LGPL-3.0-only components have no newly granted later-version option.

The image installs its project notices and preserved upstream legal catalogue in
`/usr/share/doc/life-journal/`; the Web role also serves them under `/legal/`.
`browser-notices.json` identifies the actual packages in emitted browser chunks
and includes their upstream texts verbatim. The historical notice catalogue is a
reference superset, not proof of the current binary's complete license closure.
`binary-inventory.json` records current installed package identities and notice
hashes. Neither inventory nor the presence of this notice certifies that the
corresponding-source and other binary release obligations have been completed.

Apache-2.0 components retain applicable upstream NOTICE and LICENSE texts; no
upstream trademark endorsement is implied. DOMPurify may be distributed under its
Apache-2.0 alternative, retaining its full notices. Lucide ISC / applicable Feather
MIT and Alembic MIT credits retain their original grants and attribution. No
project-wide relicense of these components is made.

This product uses the FreeType Project (https://freetype.org/). This software is
based in part on the work of the Independent JPEG Group. The applicable original
authors, years, license conditions and disclaimers must accompany the actual
libraries; these credits do not replace their notices.

Psycopg / psycopg-c are LGPL-3.0-only. The C accelerator is compiled from its
published source and dynamically linked to Debian/PGDG libpq. The separately
bundled psycopg-binary wheel and its native library bundle are not conveyed.
Recipients may modify or replace the library with an
interface-compatible version, recombine/rebuild this application, and reverse
engineer the combined work for debugging those modifications. There is no added
contractual prohibition on doing so. The Python package is dynamically imported;
its pure-Python implementation can use the installed dynamic libpq through
`PSYCOPG_IMPL=python`. See LGPL_REPLACEMENT.md for an isolated verification and
rebuild method. Source identity checks describe the original delivered artifact;
they do not restrict recipients' GPL/LGPL rights to modified builds.

The release workflow requires the complete applicable corresponding source,
patches and build/install instructions alongside the binary without an additional
charge (planned GPLv3 section 6(d) method). Merely linking upstream or this notice
is insufficient. No written source offer is being issued here. The exact
binary/source/legal pack and hashes must pass the binding gate before artifact
upload. The source package includes Pillow's LGPL FriBiDi shim, complete source
and an actual modified-source relink receipt; see SOURCE_BUILD.md,
REDISTRIBUTION.md and docs/release-v5.1.9.md. Runtime inventory flags describe the
build-time inventory only; the companion DISTRIBUTION_MANIFEST is the completed
source/notice delivery receipt for the TAR it explicitly hashes.
