<div align="center">
  <img src="docs/assets/banner.svg" alt="kinthic" width="100%" />
</div>

> **kinthic — the agent that knows how things connect.**

<div align="center">
  <a href="https://github.com/openyfai/kinthic"><img src="https://img.shields.io/github/stars/openyfai/kinthic?style=flat-square&color=312e81" alt="GitHub stars"></a>
  <a href="https://github.com/openyfai/kinthic/blob/main/LICENSE"><img src="https://img.shields.io/github/license/openyfai/kinthic?style=flat-square&color=312e81" alt="License"></a>
</div>

<div align="center">
  <em>(Demo coming soon: A 5-second visualization of kinthic traversing the graph memory)</em>
  <!-- ![Demo](docs/assets/demo.gif) -->
</div>

---

kinthic is a local-first AI agent with graph-based memory. It stores what it learns as a network of entities and relationships — so it can answer the questions flat-memory agents can't: not just *what* it knows, but *how* things are connected.

## Quickstart

```bash
curl -fsSL https://kinthic.openyf.dev/install.sh | bash
kinthic init
```
*Note: Windows requires WSL2.*

## Architecture

*(Architecture diagram coming soon: A visual representation of how memory nodes and edges operate)*
<!-- ![Architecture](docs/assets/architecture.png) -->

kinthic is designed around a rigid noun-verb CLI structure:
- `kinthic` — Initialize standard interactive loop
- `kinthic daemon start` — Boot the background supervisor
- `kinthic mcp add filesystem` — Attach local Model Context Protocol
- `kinthic skills install <name>` — Ingest new workflow capabilities

## Features

- **Absolute State:** Memory is not a vector search afterthought. It is a local, persistent causal graph.
- **Dynamic Capabilities:** Drop a Markdown file into `~/.kinthic/skills/` and the cognitive engine absorbs a new workflow instantly. No Python required.
- **Total Locality:** Your data never leaves your machine unless you explicitly grant network access.

## Comparison

| Peer | Memory model | kinthic's edge |
|------|--------------|----------------|
| OpenClaw | Flat files | Traversable entity graph |
| Hermes Agent | Vector search index | Relationship-style queries ("how are X and Y connected?") |
| **kinthic** | **Knowledge graph** | Both factual recall AND relationship reasoning |

## Contributing & Roadmap

- **Contributing**: Please read our [Contributing Guidelines](CONTRIBUTING.md) before submitting pull requests.
- **Roadmap**: See [docs/roadmap.md](docs/roadmap.md) for upcoming features and the long-term vision.

## Security

kinthic is sandboxed by default.
- Tool usage requires explicit cryptographic approval.
- Terminal execution is locked.
- File system modification is restricted.

Read the [Security Policy](SECURITY.md) before deployment.
