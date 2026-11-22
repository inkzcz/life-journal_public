# Rebuild, replace libraries, and inspect this exact delivery

The companion package and DISTRIBUTION_MANIFEST.json bind the application commit,
business TAR SHA256, image config digest, installed versions, complete source
archives, build/installation files and validation receipts. The archive contains
application source without Git history, Debian/PGDG exact .dsc + orig/patch files,
Python sdists, Cargo.lock-verified crates, binary-h1-verified Go module sources,
exact CPython/Go source and preferred source commits for emitted browser modules.
Sources and applicable legal text are offered alongside the binary, without an
additional charge. No written source offer or additional recipient restriction
is imposed. Each third-party grant remains its own grant; the original project
notice applies only to owner-controlled original code and increments.

## Application and database library

Extract application/life-journal-source.tar.gz. Build using its root Dockerfile
with Linux/amd64 BuildKit. The pinned FROM digests, constraints-release.txt,
requirements and build scripts are part of that source. There is no default
`--pull` or Registry push. The three commands `api`, `web`, `maintenance` reuse
one business image. A PostgreSQL database image is not included or needed for
the business image build; install that database independently.

Psycopg 3.3.9 / psycopg-c 3.3.9 are LGPL-3.0-only. The C accelerator is built
from its published SHA256-bound sdist with gcc against Debian/PGDG libpq headers;
the image dynamically loads libpq.so.5. No psycopg-binary libraries are conveyed.
The exact sdist, .dsc patches, compilation/install commands and compiler/libpq
configuration receipts are supplied. Modify the library's source and rebuild
with the same Dockerfile, changing the constraints/version honestly as needed.
Or set PSYCOPG_IMPL=python and put an interface-compatible modified Python copy
before the installed package on PYTHONPATH. The isolated actual PG17 query drill
loads and executes such a modified library. Users may reverse engineer the
combined work to debug library modifications. Official artifact identity checks
are not a prohibition on lawful modified builds.

## Pillow and the LGPL FriBiDi shim

Pillow retains MIT-CMU and the bundled components' own grants. Its upstream SBOM
declares the small src/thirdparty/fribidi-shim files LGPL-2.1-or-later. The exact
unmodified files are included in the provided Pillow sdist; full Pillow source,
its preferred upstream source/build recipe, LGPL/GPL texts, upstream FriBiDi
ancestry/credits and compilation instructions accompany the binary. This is a
complete-source/relink method, not a claim that statically compiled code can be
replaced by merely setting a Python environment variable.

The supplied tests/pillow_relink_probe.py makes a compatible logging modification
to load_fribidi(), compiles a new Pillow wheel with `raqm=enable`, `raqm=vendor`,
`fribidi=vendor` and Debian development headers, installs it in a new directory,
and loads it as UID/GID10001. It checks execution of that modified shim, the
Pillow/font interface and a JPEG round trip. No production image or installed
library is changed by this test. The default production image retains its
upstream JPEG/PNG/WebP/AVIF implementation; this relink test does not claim
bit-identical rebuilds or every possible ABI modification.

To repeat that relink, use the provided script and exact Pillow sdist inside a
new disposable container as documented by scripts/test_pillow_relink.py. That
wrapper accepts only new RUNNER_TEMP source paths and mounts three read-only files,
never a deployment path, Docker socket, database or media. A normal replacement
image can instead COPY an interface-compatible rebuilt Pillow library into its
venv, or install a rebuilt wheel using pip. Ordinary Python module loading is
retained. Existing image and source licenses allow these modifications.

## Debian and other independent programs

For each supplied .dsc, place its sibling orig/debian/diff files together and
run `dpkg-source -x PACKAGE.dsc` in a build directory. The resulting debian/rules,
patches, source and build dependencies describe Debian's build/install recipe.
Use Debian/PGDG's exact source version from sources.json, not a similarly named
latest release. Source descriptors are fetched from the exact public archive;
TLS, descriptor identity and all published archive checksums are verified.
The snapshot SHA1 is a content locator, supplemented by the descriptor SHA256;
this is not described as an uploader-signature or APT-index verification.

General-purpose build tools can be installed independently. CPython's exact
source hash comes from the pinned base image; configure/build history is provided
by the Docker recipe and actual receipts. Go's official source checksum and all
named module h1 values match the Caddy binary metadata. Caddy's small generated
root imports `github.com/caddyserver/caddy/v2/cmd` and blank-imports
`github.com/caddyserver/caddy/v2/modules/standard`; its main calls caddycmd.Main().
The supplied core module includes those sources, module build files and standard
modules. All named dependency source zips, notices and Go runtime source accompany
it. Apache-2.0 notices and trademarks remain upstream's. No bit-identical Caddy
rebuild is promised or needed for its permissive grant.

Browser chunks include only the enumerated runtime packages in browser-notices.
Their integrity-checked npm artifacts and exact upstream preferred source commits
are both provided. Rebuild with the application's package-lock.json and Node22;
general-purpose tools need not be copied into the runtime image. Two historical
unbundled npm tool notice gaps are excluded from this source delivery, not waived.
Rust dependency archives match the supplied source Cargo.lock checksums; upstream
MIT/Apache/Unicode/other applicable notices are retained.

The source archives may contain upstream public self-test keys/images and public
copyright names. These are official upstream materials, not Life Journal private
data. Source collection never reads a NAS, database, backup or user media. Project
source Gitleaks and image all-layer key checks are recorded separately; neither
claims to recognize every possible unknown secret format.
