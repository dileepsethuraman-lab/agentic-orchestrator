1. System Topology Overview
This system is an Asynchronous, Cache-First Automated Orchestration Engine for a Telecom company designed to handle high-throughput (5 TPS) telecom workloads using cloud-based reasoning (Deepseek). It maintains 100% data sovereignty by filtering and resolving repetitive transactions locally inside your network perimeter, reserving cloud calls strictly for complex, unmapped operational anomalies.

2. End-to-End Component Lifecycle

Phase A: Traffic Ingestion & Serialization (External to hermes)
API Ingestion Gateway: Receives structured carrier payloads (TMF640/641 JSON) or raw unstructured text strings.
RabbitMQ Buffer Queue: Absorbs sudden traffic surges. It queues tasks to prevent transaction drops and feeds them to the worker nodes using a fair-dispatch pattern (prefetch_count=1).

Phase B: Horizontal Worker Processing (Internal to Hermes)
Multi-Worker Pool: Parallel, lightweight Python worker containers pull tasks concurrently from RabbitMQ.
Local Redis Cache Scanner: The active worker executes a native Python script to test key matches against a local Redis Cache database, bypassing the AI engine completely on known tasks (0ms LLM AI token latency).

Phase C: Branch Routing Optimization (Internal to Hermes)
Phase C - Track A: The 5ms Fast Path (Cache Hit)
The worker pulls the pre-saved template directly from Redis memory.
Local utility functions extract fields and hydrate the template variables natively inside your perimeter.
Phase C - Track B: The Secure Fallback Path (Cache Miss)
Data Masker: A local script tokenizes sensitive fields, swapping real network IPs and chassis hostnames out for generic variables (e.g., VAR_IP_1).
Hermes Core RAG: The cloud-hosted agent runs a local document lookup against your vendor manuals, injecting reference context into Deepseek.
Deepseek: The model evaluates the document rules and returns an abstract, reusable template blueprint.
Memory Write-Through: The worker captures Deepseek's new blueprint and writes it back to the local Redis database so that identical future requests scale down the 5ms Fast Path.
Local Hydrator: The local worker matches the session tokens and re-injects the real network target parameters.

Phase D: Hard Gate Verification & Invocation
Local Validation Gateway: Both tracks converge at an ironclad programmatic Pydantic v2 validation script that tests variable range boundaries and runs regex filters to drop hazardous inputs before they execute.
Model Context Protocol (MCP) Server: The validated blueprint passes to your local MCP server. It maps the clean JSON array directly into direct node protocols (SSH CLI, SOAP XML, Netconf), completing the physical infrastructure configuration update on your routers and elements.
Queue Acknowledgement: A final completion handshake deletes the original message from the RabbitMQ buffer table.

3. Structural Security Guardrails
a) Data Anonymization Gate:
Cloud LLM layers never see unmasked carrier data. Sensitive infrastructure keys (IP subnets, chassis IDs, customer account numbers) are stripped at the local edge and mapped to temporary tracking hashes that exist only inside your local server's transient memory.

b) Deterministic Code Firewall:
AI outputs are non-deterministic and can hallucinate. The Local Validation Gateway treats all generated plans as untrusted payloads. It runs compiled, hardcoded schema logic blocks to intercept and abort malformed commands before they interface with physical hardware.

d) Destructive Keyword Filtering:
The validation scanner uses rigid regex patterns to scan command strings. If an execution string contains prohibited words (e.g., erase, reload, format, shutdown, no switchport), the entire transaction drops instantly and triggers an alert.

e) Explicit Range Constraints:
Numeric values must pass binary threshold filters defined by your engineering team (e.g., forcing VLAN IDs to sit strictly within the 1-4094 block). Any payload exceeding these constraints causes an immediate validation failure.