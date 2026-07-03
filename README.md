<div align="center">
  <img src="docs/assets/banner.jpg" alt="Kronos" width="100%" />
</div>

# Kronos

**Kronos is a local, persistent cognitive engine.**

Most AI agents are stateless scripts. They forget you the moment the terminal closes. They compete on context windows; Kronos competes on state. 

Built on the **Silex** memory engine, Kronos constructs a causal knowledge graph of its interactions, learns workflows via dynamic skills, and exposes its Epistemic Topology in real-time through a dedicated Next.js dashboard.

It is 0 to 1. It does not compete with generic wrappers. It replaces them.

---

### The Paradigm

- **Absolute State:** Memory is not a vector search afterthought. It is a local, persistent causal graph.
- **Dynamic Capabilities:** Drop a Markdown file into `~/.kronos/skills/` and the cognitive engine absorbs a new workflow instantly. No Python required.
- **Total Locality:** Your data never leaves your machine unless you explicitly grant network access.
- **Ubiquitous Access:** Run the terminal agent at your desk, or deploy `kronos channels telegram run` to interface with your engine from your phone.

---

### Initialization

The system is designed for modern development environments. 

```bash
curl -fsSL https://kronos.openyf.dev/install.sh | bash
kronos init
```

*Note: Windows requires WSL2.*

To initialize the full stack (FastAPI Backend + Topology Dashboard + Telegram Worker):
```bash
docker-compose up -d
```
Access the cognitive topology at `http://localhost:3000`.

---

### Architecture

Manage the engine through a rigid noun-verb CLI structure:

```bash
kronos                        # Initialize standard interactive loop
kronos daemon start           # Boot the background supervisor
kronos channels telegram run  # Engage mobile channel 
kronos mcp add filesystem     # Attach local Model Context Protocol
kronos skills install <name>  # Ingest new workflow capabilities
```

For the complete architectural spec, read the [CLI Reference](docs/cli_reference.md).

---

### Security

Kronos is sandboxed by default.
- Tool usage requires explicit cryptographic approval.
- Terminal execution is locked.
- File system modification is restricted.

Read the [Security Policy](SECURITY.md) before deployment.

---

*Built by [OpenYF AI](https://x.com/openyfai).*
