# Telecom Service-Resource Orchestrator — Core Ontology

> Version 1.0 | Domain: Telecommunications OSS/BSS
> Standards alignment: TM Forum SID (Information Framework), MEF LSO, ETSI NFV MANO, IETF YANG

## 1. Domain Entity Hierarchy

```
Customer
  └─ ProductOrder ─── instantiates ──→ Service
                                         ├── CustomerFacingService (CFS)
                                         │     e.g. "Enterprise VPN for Acme Corp"
                                         └── ResourceFacingService (RFS)
                                               e.g. "L3VPN instance on PE routers"
                                                 └─ Resource (physical / virtual / cloud)
                                                       ├── PhysicalResource
                                                       │     ├── NetworkDevice (router, switch, firewall, OLT, etc.)
                                                       │     ├── Port / Interface
                                                       │     ├── Card / Module / Chassis
                                                       │     └── PhysicalLink (fiber, copper, microwave)
                                                       ├── LogicalResource
                                                       │     ├── VLAN, VRF, VXLAN, VPN instance
                                                       │     ├── IP Subnet / Address Pool
                                                       │     ├── BGP / OSPF / ISIS process
                                                       │     ├── QoS Policy / ACL
                                                       │     └── Routing table entry
                                                       └── VirtualResource (NFV / Cloud)
                                                             ├── VNF (vRouter, vFirewall, vCPE, vDPI)
                                                             ├── CNF (containerised network function)
                                                             ├── VirtualLink
                                                             └── VirtualStorage
```

## 2. Key Relationship Types

| Relationship    | From          | To           | Meaning                                    |
|-----------------|---------------|--------------|--------------------------------------------|
| `instantiates`  | ProductOrder  | Service      | Order creates a service instance           |
| `composes`      | Service       | Service      | CFS is composed of one or more RFS         |
| `realised_by`   | RFS           | Resource     | A resource-facing service runs on resources|
| `hosts`         | Device        | VNF          | Physical device hosts a virtual function   |
| `connects_to`   | Resource      | Resource     | Network adjacency (link, tunnel, peer)     |
| `depends_on`    | Resource      | Resource     | Requires another resource to function      |
| `allocates_from`| Resource      | Pool         | Draws from a shared capacity pool          |
| `terminates_on` | Service       | Interface    | Service endpoint lands on a port           |
| `provisioned_by`| Resource      | Workflow     | Resource was created by a workflow         |

## 3. Lifecycle State Machine

### Service Lifecycle (per MEF LSO + TM Forum eTOM)

```
DESIGNED → FEASIBILITY_CHECKED → RESERVED → PROVISIONING → ACTIVE
                                                         ├──→ SUSPENDED
                                                         ├──→ MODIFYING → ACTIVE
                                                         └──→ TERMINATING → TERMINATED
```

### Resource Lifecycle (per ETSI NFV MANO)

```
PLANNED → ALLOCATED → CONFIGURING → IN_SERVICE
                                  ├──→ MAINTENANCE → IN_SERVICE
                                  ├──→ DEGRADED → IN_SERVICE
                                  └──→ DECOMMISSIONING → DECOMMISSIONED
```

## 4. Service Taxonomy (Common Telecom Products)

| Category              | Example Services                               | Key Resources Involved                              |
|-----------------------|------------------------------------------------|-----------------------------------------------------|
| L3VPN / MPLS VPN      | Enterprise MPLS L3VPN, VPLS, EVPN             | PE router, VRF, BGP session, CE interface, RT/RD    |
| SD-WAN                | Managed SD-WAN overlay                        | vCPE/uCPE, IPSec tunnels, SD-WAN controller         |
| Internet Access       | DIA, Broadband, FTTH, 5G FWA                  | BNG/BRAS, OLT, ONT, IP pool, AAA (RADIUS)           |
| Cloud Connect         | AWS Direct Connect, Azure ExpressRoute        | Physical cross-connect, VLAN handoff, BGP           |
| Voice / UC            | SIP trunk, Hosted PBX, Microsoft Teams Direct Routing | SBC, SIP trunk, DID range, media server      |
| Mobile Backhaul       | 4G/5G xHaul, Fronthaul                        | Cell-site router, microwave, fiber, PTP, SyncE      |
| Security              | Managed Firewall, DDoS scrubbing, SASE        | vFirewall, scrubbing center, BGP flowspec           |
| Transport / Wavelength| OTN circuit, Dark fiber, Wavelength service   | ROADM, transponder, muxponder, fiber pair           |

## 5. Resource Taxonomy (Down to Network Level)

### Layer 0-1 (Photonic / Physical)
- Fiber strand, Fiber pair, Duct, Manhole, Splice enclosure
- Wavelength / Lambda, OTU, ODU, OCH trail
- ROADM degree, WSS port, Amplifier, Transponder

### Layer 2 (Data Link)
- Switch, Bridge domain, VLAN (C-VLAN, S-VLAN, Q-in-Q)
- Pseudowire (PWE3), VPLS instance, EVPN instance (EVI)
- LAG / Port-channel, STP domain, MAC address table

### Layer 3 (Network)
- Router, VRF, BGP ASN / peer / session, OSPF area / process
- IP subnet, Loopback, Route policy / Route-map
- MPLS LSP, RSVP-TE tunnel, SR-MPLS segment list, SRv6 path

### Layer 4-7 (Application)
- Firewall policy / zone, Load balancer VIP / pool, SBC, DPI engine
- DNS zone / record, NTP peer, RADIUS / TACACS+ server
- Certificate, SNMP community, NetFlow exporter

### Cloud / NFV
- VIM resource (OpenStack compute/network/storage), Kubernetes Pod/Service
- VNF Descriptor (VNFD), Network Service Descriptor (NSD)
- Virtual link, SRIOV VF, DPDK port, vSwitch

## 6. Workflow Categories

| Workflow Type          | Trigger                          | Description                                      |
|------------------------|----------------------------------|--------------------------------------------------|
| Service Fulfillment    | "Create service X for customer Y"| End-to-end provisioning from order to activation |
| Service Assurance      | Alarm, threshold breach, cron    | Health check, fault correlation, remediation     |
| Resource Provisioning  | Resource creation step in a workflow | Configure a single resource (interface, VRF, etc.) |
| Resource Discovery     | Cron, manual trigger             | Scan network, sync inventory                     |
| Capacity Management    | Threshold, forecast              | Augment pool, migrate load                       |
| Service Modification   | Customer request                 | Add/remove/change service component              |
| Service Termination    | Customer request, contract end   | Decommission service, release resources           |

## 7. Descriptor Formats

| Format   | Scope              | Standard              | Used For                                          |
|----------|--------------------|-----------------------|---------------------------------------------------|
| TOSCA    | Service topology   | OASIS TOSCA           | Service template, VNF forwarding graph            |
| YANG     | Device/resource config | IETF YANG / NETCONF | Device configuration, resource state              |
| NSD      | Network service    | ETSI NFV SOL-006      | VNF composition, virtual links                    |
| VNFD     | Virtual function   | ETSI NFV SOL-001      | VNF deployment descriptor                         |
| Helm     | CNF                | CNCF                  | Containerised network function deployment         |
| Ansible  | Automation         | Red Hat               | Device configuration playbooks                    |
