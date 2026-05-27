# Local Preview

Install the development dependencies:

```bash
python3 -m pip install -r requirements-dev.txt
```

Start the local documentation server:

```bash
python3 -m mkdocs serve
```

Build the static site:

```bash
python3 -m mkdocs build --strict
```

The generated site is written to `build/mkdocs-site/`.
