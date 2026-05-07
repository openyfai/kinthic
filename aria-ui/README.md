# ARIA UI

This is the static-export Next.js frontend for ARIA.

It is served by the Python web server after build output is written to `aria-ui/out`.

Use Node `20` for local development and builds.

The main installation and launch instructions live in the root [`README.md`](../README.md).

## Local Development

```bash
npm install
npm run dev
```

If you are running the Python backend on another origin, set:

```bash
NEXT_PUBLIC_ARIA_API_BASE=http://127.0.0.1:8000
```

## Production Build

```bash
npm run build
```

The project uses `output: "export"` in `next.config.ts`, so the built site can be mounted by FastAPI.

## UI Areas

- Chat
- Goals
- Knowledge Graph
- Operator Panel
- Settings
- First-run onboarding

## Notes

- REST auth uses `Authorization: Bearer <api-key>`.
- WebSocket auth uses an initial handshake message instead of query-string tokens.
- Browser-local connection settings are stored in `localStorage`.
