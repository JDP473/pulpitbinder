# Working on Pulpit Binder

Owner: Jarred Pettijohn, pulpit minister at Bridge Creek church of Christ, also a developer (Laravel, C#, SQL).

## Publishing (most important)

- The app is one file, `pulpit-binder.html`, published as a Claude artifact at https://claude.ai/artifact/6mMDoGKaPf3qKzRHE9mMUn
- Always publish updates to that URL (Artifact publish with `file_path: pulpit-binder.html` and `url` set to the link above, after reading it if this conversation has not published it yet). Never create a new artifact: his synced sermons live under that page, and a new page would start empty.
- Leave `capabilities` out of publishes so the current set carries forward: sample, downloads, db, user, assets, and mcp (Firecrawl `firecrawl_scrape`; Canva `generate-image`, `get-generate-image-job`, `search-designs`, `create-design`, `get-create-design-async-job`, `read-design`, `edit-design`, `export-design`; Pulpit Live `live_open`, `live_slide`, `live_show`, `live_close`; Obsidian `read_note`, `write_note`, `delete_note`). Adding a connector means passing the whole set once.
- Order of work: edit, syntax-check the script, run the relevant browser test, commit, publish, push.

Syntax check:
```bash
python3 -c "s=open('pulpit-binder.html').read(); i=s.rfind('<script>'); open('/tmp/pb.js','w').write(s[i+8:s.rfind('</script>')])" && node --check /tmp/pb.js
```

## Constraints of the Claude-hosted page

- External scripts only from approved CDNs (JSZip 3.10.1 and pdf.js 3.11.174 from cdnjs). External images and fetch are blocked; plain links work.
- Claude calls go through `claude.use("sample")`, sync through `claude.use("db")`, files through `claude.use("assets")`, Canva and Firecrawl through `claude.use("mcp")`. Every feature must degrade gracefully when one of these is missing.
- Browser storage is a convenience only; durable data goes through db and assets.

## Never commit

- Sermon content, recordings, or anything from his account.
- Copyrighted Bible text (ESV, LSB, NASB, NKJV). Test fixtures must stay generic.
- API keys or signed media URLs.

## Writing in the app and in replies

- No emojis. Use commas rather than em dashes where possible.
- Plain, pastoral wording. "church of Christ" with a lowercase "church". Claude prompts in the app are written for a preacher in the churches of Christ.
- Default translation ESV; favorites ESV, LSB, NASB, NKJV.

## Testing

Browser tests mock `window.claude` with an init script and serve the page from a fake origin; see `tests/browser/pk.py` for the pattern. Look at the screenshots in `tests/out/`, not only the printed checks, and check light, dark, and a 390px-wide phone.
