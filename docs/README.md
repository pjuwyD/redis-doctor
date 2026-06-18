# Redis Doctor documentation

- **Source:** Markdown lives in [`md/`](md/). Start at [`md/index.md`](md/index.md).
- **Built site:** HTML is generated into `html/` by the converter below. Open
  `html/index.html` in a browser.
- **Converter:** [`tools/converter.py`](tools/converter.py) — a stdlib-only
  Markdown → HTML builder (nav sidebar, prev/next, heading anchors, `.md`→`.html`
  link rewriting).

## Build the HTML

```bash
python docs/tools/converter.py            # build docs/md -> docs/html
python docs/tools/converter.py --clean    # wipe docs/html first, then build
python docs/tools/converter.py --src <dir> --out <dir>
```

No third-party dependencies are required to build the docs.

## Editing

- Add a page by creating a new `md/<path>.md`. It is picked up automatically and
  appended under "More" in the sidebar.
- To place it in a specific section/order, add its path to the `NAV` table near the
  top of `tools/converter.py`.
- Cross-link other pages with normal relative Markdown links to the `.md` file
  (optionally with `#anchor`); the converter rewrites them to `.html`.
- Re-run the converter after editing.

## Supported Markdown

ATX headings (with auto anchors), paragraphs, fenced code blocks, inline
code/bold/italic/links, GFM pipe tables, ordered/unordered lists (one nesting
level), blockquotes, and horizontal rules.
