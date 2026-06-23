# Documentation

> Telecom Agentic Orchestration Engine — Proof of Concept & End-State Architecture

## Directory Structure

```
documentation/
├── README.md                              ← This file
├── build-prompts/                         ← Agent build instructions
│   ├── PoC-prescriptive-build-prompt.md   # Prescriptive: exact code, paths, CSS rules
│   └── PoC-behavioral-specification.md    # Generic: behavioral spec, implementation-agnostic
├── end-state/                             ← Target production architecture
│   ├── architectural-blueprint.md         # Master architecture: topology, sequences, deployment
│   ├── api-specification.md               # 30+ endpoints (TMF622/641/640/638/639 + internal)
│   ├── component-specification.md         # 47-file modular src/ tree, 35+ component specs
│   ├── solution-design.md                 # Design philosophy, segment×SLA reasoning, trade-offs
│   └── component-diagram.md               # Standalone ~70-node Mermaid component diagram
└── diagrams/                              ← Visual artifacts
    └── architecture-component-diagram.html # Dark-themed SVG (opens in any browser)
```

## Quick Reference

| Document | Audience | Purpose |
|----------|----------|---------|
| `build-prompts/PoC-prescriptive-build-prompt.md` | AI agents | Reproduce the PoC exactly — every line of code specified |
| `build-prompts/PoC-behavioral-specification.md` | AI agents | Build a functionally identical PoC independently |
| `end-state/architectural-blueprint.md` | Architects, engineers | Understand the full production target architecture |
| `end-state/api-specification.md` | Integration engineers | Implement CRM-facing and internal APIs |
| `end-state/component-specification.md` | Developers | Build individual modules with class signatures and DB schemas |
| `end-state/solution-design.md` | Solution architects, stakeholders | Understand design decisions and trade-offs |
| `end-state/component-diagram.md` | Everyone | Visual overview of all system components |
| `diagrams/architecture-component-diagram.html` | Everyone | Browser-renderable SVG architecture diagram |

## Related Documentation

- **PoC Source:** `poc/server_live.py` (1,848 lines)
- **Web UI:** `poc/static/index.html` (727 lines)
- **Knowledge Base:** `knowledge-base/` (ontologies, standards, references)
- **System Docs:** `knowledge-base/system-docs/` (component specs, architecture, API, solution)
