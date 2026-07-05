# Mintlify deployment

Public docs live at **https://docs.kinthic.com**, built from this repository's `docs/` folder.

## One-time setup

1. Create a [Mintlify](https://mintlify.com) account.
2. Connect the GitHub repository `openyfai/kinthic`.
3. Set the **docs directory** to `/docs` (contains `docs.json`).
4. Add custom domain `docs.kinthic.com` in Mintlify dashboard.
5. Add DNS record at your registrar:

   | Type | Name | Value |
   |------|------|-------|
   | CNAME | `docs` | *(target shown in Mintlify dashboard)* |

6. Wait for SSL provisioning (usually minutes).

## Local preview

Install the Mintlify CLI:

```bash
npm i -g mintlify
cd docs
mintlify dev
```

Opens preview at `http://localhost:3000`.

Validate links:

```bash
mintlify broken-links
```

## Publishing

Mintlify auto-deploys on push to the connected branch (typically `main`).

After merge:

```bash
curl -I https://docs.kinthic.com
curl -fsSL https://docs.kinthic.com/llms.txt | head
```

## Adding pages

1. Create `docs/<section>/<page>.mdx` with frontmatter (`title`, `description`).
2. Add the page path to `docs/docs.json` navigation.
3. Use root-relative links: `[Daemon](/guides/daemon)` — no `.md` suffix.
4. Push to `main`.

## Internal docs (not published)

Files in `docs/planning/`, `docs/blog/`, checklists, and RFCs are **not** listed in `docs.json` and do not appear in the public site.
