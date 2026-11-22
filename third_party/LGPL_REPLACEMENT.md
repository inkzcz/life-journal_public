# Psycopg replacement and recombination

Psycopg remains LGPL-3.0-only; this project adds no reverse-engineering restriction
for debugging changes to that library. The application imports it dynamically.
The default psycopg-binary accelerator and its bundled libraries still require
their own exact-source/build/license review before binary publication.

An interface-compatible replacement can be installed when rebuilding the image,
or imported before the installed copy through `PYTHONPATH`. Setting
`PSYCOPG_IMPL=python` selects Psycopg's own Python implementation and dynamically
loads the system libpq, avoiding use of the binary accelerator in that run. This
does not exempt libraries still present in the delivered layers from their own
source and notice obligations. Record modified build provenance accurately;
official identity verification is not a prohibition on modified versions.

The isolated Docker acceptance runner now executes
`tests/lgpl_replacement_probe.py` in its own synthetic maintenance container:

1. UID/GID10001 copies the installed Python library to a fresh private `/tmp`
   directory; its installed files and any data mounts remain untouched.
2. A compatible wrapper around `Connection.execute` counts invocations.
3. A child Python interpreter imports the modified copy using `PYTHONPATH` and
   `PSYCOPG_IMPL=python`; it checks the exact import path and implementation.
4. It performs a read-only query against the runner's synthetic PG17 database
   and confirms that the modified method actually executed.
5. The child exits and the temporary library copy is removed. Failure fails the
   Docker acceptance; the script refuses to run without explicit synthetic opt-in.

Reproduce on a new local test project only, after building a candidate and
independently preparing the official PG17 image:

```sh
python tests/docker_installation.py --image-tag v5.1.9-candidate.COMMIT \
  --output /PRIVATE/NEW/installation-report.json
```

The successful report must contain `lgpl_replacement.interface_compatible_query`
equal to `passed`. This exercises a supported replacement path, not all possible
future ABI changes. It does not alone complete LGPL section 4: the exact Library
Corresponding Source, required GPL/LGPL texts, combined-work notices and a usable
recombination/install path must accompany the reviewed release. See the binary
obligation matrix in REDISTRIBUTION.md. No source offer or release is made by
this test or documentation.
