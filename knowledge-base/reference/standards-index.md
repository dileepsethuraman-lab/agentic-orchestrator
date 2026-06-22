# Telecom Orchestrator — Reference Standards Index

## Industry Standards Bodies & Frameworks

### TM Forum (TeleManagement Forum)
- **eTOM** (enhanced Telecom Operations Map) — Business process framework
- **SID** (Information Framework) — Shared Information/Data model
- **TAM** (Application Framework) — Application map
- **Open APIs** — REST-based API suite (TMF638 Service Inventory, TMF639 Resource Inventory, TMF641 Service Ordering, etc.)
- URL: https://www.tmforum.org

### MEF (formerly Metro Ethernet Forum)
- **MEF 55** — LSO Reference Architecture and Framework
- **MEF 59** — Network Resource Management: Information Model
- **MEF 60** — Network Resource Provisioning: Interface Profile
- **MEF 63** — Subscriber Service Attributes (for SD-WAN, etc.)
- **MEF W117 / LSO Sonata** — Inter-provider orchestration interface
- URL: https://wiki.mef.net

### ETSI NFV ISG
- **NFV-MANO** — Management and Orchestration (NFVO, VNFM, VIM)
- **SOL-001** — VNF Descriptor (TOSCA-based)
- **SOL-006** — YANG-based NFV descriptors (NSD, VNFD, PNFD)
- **SOL-003** — NFVO-VNFM interface (Or-Vnfm)
- **SOL-005** — Os-Ma-nfvo interface
- URL: https://www.etsi.org

### IETF
- **YANG** (RFC 7950) — Data modeling language for NETCONF/RESTCONF
- **NETCONF** (RFC 6241) — Network configuration protocol
- **RESTCONF** (RFC 8040) — REST interface for YANG datastores
- **L3VPN YANG model** (RFC 8299) — L3VPN service delivery model
- **L2VPN YANG model** (RFC 8466)
- URL: https://www.ietf.org

### ONF (Open Networking Foundation)
- **TAPI** (Transport API) — Optical/transport SDN controller northbound
- **CIM** (Core Information Model)
- URL: https://opennetworking.org

### 3GPP
- **TS 28.530/531** — Management and orchestration for 5G (5G MANO)
- **TS 28.540** — Network Resource Model (NRM) for 5G
- URL: https://www.3gpp.org

### OASIS TOSCA
- **TOSCA Simple Profile for NFV** — Network service topology templates
- URL: https://www.oasis-open.org

## Key Open-Source Implementations

| Project          | Scope                        | URL                                   |
|------------------|------------------------------|---------------------------------------|
| OSM              | ETSI MANO NFVO/VNFM          | https://osm.etsi.org                 |
| ONAP             | Full OSS orchestration       | https://onap.org                     |
| OpenStack Tacker | NFV Orchestrator (VNFM)      | https://wiki.openstack.org/wiki/Tacker|
| Nephio           | K8s-based 5G NF automation   | https://nephio.org                   |
| Cisco NSO        | Multi-vendor service activation | https://developer.cisco.com/nso   |
| Ansible (network)| Device config automation     | https://docs.ansible.com/ansible/latest/network|
| Nornir           | Python automation framework  | https://nornir.readthedocs.io        |
| NetBox           | DCIM / IPAM / network source of truth | https://netbox.dev          |
| Nautobot         | NetBox fork + orchestration  | https://nautobot.com                 |
| Itential         | Network automation platform  | https://www.itential.com             |

## Key Protocol Stack

```
Northbound (OSS/BSS):    REST / TMF Open API / MEF LSO Sonata
                          ↓
Service Orchestrator:     TOSCA NSD / Helm Chart / Custom DSL
                          ↓
Resource Orchestrator:    YANG + NETCONF / RESTCONF / gNMI
                          ↓
Controllers:              SDN Controller (ODL, ONOS) / NFV VNFM
                          ↓
Device / Infrastructure:  CLI (SSH), SNMP, gRPC, NETCONF, RESTCONF
```
