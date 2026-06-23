# Telecom Agentic Orchestration Engine — Java PoC

> Built from `PoC-behavioral-specification.md` — a fully independent implementation.

## Quick Start

```bash
# Requires Java 21+ and Maven 3.9+
cd /opt/data/telecom-orchestrator-java
mvn spring-boot:run
```

Server starts on **port 8091** (isolated from the Python PoC on 8090).

## Architecture

| Component | Package | Purpose |
|-----------|---------|---------|
| `Application` | `com.telecom.orchestrator` | Spring Boot entry point |
| `OrchestratorController` | `api` | 8 REST endpoints |
| `PipelineEngine` | `pipeline` | 12-stage async pipeline |
| `DataMasker` | `security` | MSISDN/IP regex tokenization |
| `KnowledgeBase` | `store` | 4 service domains, workflow mappings |
| `PatternStore` | `store` | RDF triples, Jaccard matching |
| `ServiceModelStore` | `store` | Corruption detection, diff computation |
| `SubscriberLock` | `store` | Advisory locking (TTL 30s) |
| `LifecycleNotifier` | `notification` | TMF641 milestone + state change events |

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/process` | Submit provisioning request |
| `GET` | `/api/process/{id}` | Poll pipeline result |
| `GET` | `/api/patterns` | List learned patterns |
| `GET` | `/api/patterns/{id}` | Pattern details |
| `POST` | `/api/patterns/teach` | Manual pattern injection |
| `GET` | `/api/samples` | Sample request payloads |
| `GET` | `/health` | Health check |
| `GET` | `/` | Web UI trace viewer |

## Technology Stack

- **Java 21** with Spring Boot 3.3
- **H2 embedded database** (file-persisted, zero system deps)
- **Jackson** for JSON serialization
- **Embedded Tomcat** (no external web server needed)
- **Maven** for build management
