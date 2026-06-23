package com.telecom.orchestrator.store;

import java.util.*;

/**
 * Telecom domain knowledge — static definitions of service resources,
 * workflow mappings, blocked keywords, instance attributes, and seed patterns.
 */
public final class KnowledgeBase {

    public KnowledgeBase() {}

    // ──────────────────────────────────────────────
    //  Inner types
    // ──────────────────────────────────────────────

    public record ResourceDef(String type, String role, List<String> attributes) {}

    public record ServiceResourceDef(
            String domain,
            List<String> standards,
            List<ResourceDef> requiredResources,
            String lifecycle) {}

    // ──────────────────────────────────────────────
    //  SERVICE_RESOURCES
    // ──────────────────────────────────────────────

    public static final Map<String, ServiceResourceDef> SERVICE_RESOURCES;

    static {
        SERVICE_RESOURCES = new LinkedHashMap<>();

        // ── Mobile ──────────────────────────────────────────
        SERVICE_RESOURCES.put("mobile", new ServiceResourceDef(
                "mobile",
                List.of("3GPP TS 23.002", "3GPP TS 29.002", "3GPP TS 23.401"),
                List.of(
                        new ResourceDef("HLR/HSS", "subscriber-registry",
                                List.of("msisdn", "imsi", "subscriber_profile", "roaming_profile")),
                        new ResourceDef("IMS-Core", "ims-control",
                                List.of("msisdn", "imsi", "volte_enabled", "codec_profile")),
                        new ResourceDef("PCRF/PCF", "policy-control",
                                List.of("apn", "qos_profile", "charging_rule", "bandwidth_limit")),
                        new ResourceDef("SMSC", "messaging",
                                List.of("msisdn", "routing", "validity_period")),
                        new ResourceDef("MSC/MME", "mobility",
                                List.of("msisdn", "imsi", "location_area", "tac")),
                        new ResourceDef("SBC", "session-border",
                                List.of("sip_domain", "codec_list", "media_handling"))
                ),
                "DESIGNED → FEASIBILITY_CHECKED → HLR_PROVISIONED → IMS_REGISTERED → PCRF_CONFIGURED → ACTIVE"
        ));

        // ── L3VPN ───────────────────────────────────────────
        SERVICE_RESOURCES.put("l3vpn", new ServiceResourceDef(
                "l3vpn",
                List.of("RFC 4364", "RFC 2547", "RFC 4761"),
                List.of(
                        new ResourceDef("PE Router", "provider-edge",
                                List.of("vrf_name", "rd", "rt_import", "rt_export", "bgp_peer")),
                        new ResourceDef("Route Reflector", "route-reflection",
                                List.of("cluster_id", "peer_group", "asn")),
                        new ResourceDef("VRF Instance", "virtual-routing",
                                List.of("vrf_name", "rd", "route_targets", "interfaces")),
                        new ResourceDef("NMS", "monitoring",
                                List.of("snmp_community", "syslog_server", "netflow_collector"))
                ),
                "DESIGNED → FEASIBILITY_CHECKED → RESOURCE_ALLOCATED → DEVICE_CONFIGURED → PEERING_ESTABLISHED → ACTIVE"
        ));

        // ── SD-WAN ──────────────────────────────────────────
        SERVICE_RESOURCES.put("sdwan", new ServiceResourceDef(
                "sdwan",
                List.of("MEF 70", "ONF SD-Core"),
                List.of(
                        new ResourceDef("vCPE/uCPE", "customer-premises",
                                List.of("transport_links", "encryption", "app_policy", "wan_interfaces")),
                        new ResourceDef("SD-WAN Controller", "central-control",
                                List.of("policy_set", "site_list", "template")),
                        new ResourceDef("Orchestrator", "orchestration",
                                List.of("ztp_url", "bootstrap_config", "license_key"))
                ),
                "DESIGNED → FEASIBILITY_CHECKED → CPE_DEPLOYED → TUNNELS_ESTABLISHED → POLICIES_APPLIED → ACTIVE"
        ));

        // ── Broadband ───────────────────────────────────────
        SERVICE_RESOURCES.put("broadband", new ServiceResourceDef(
                "broadband",
                List.of("ITU-T G.984", "TR-069", "TR-101"),
                List.of(
                        new ResourceDef("OLT", "optical-line-terminal",
                                List.of("ont_model", "vlan", "speed_profile", "dba_profile")),
                        new ResourceDef("BNG/BRAS", "broadband-gateway",
                                List.of("ip_pool", "subscriber_profile", "qos_policy")),
                        new ResourceDef("RADIUS", "authentication",
                                List.of("nas_identifier", "shared_secret", "auth_method")),
                        new ResourceDef("EMS", "element-management",
                                List.of("snmp_community", "trap_destinations"))
                ),
                "DESIGNED → FEASIBILITY_CHECKED → ONT_PROVISIONED → VLAN_ASSIGNED → IP_ALLOCATED → ACTIVE"
        ));
    }

    // ──────────────────────────────────────────────
    //  WF_MAP  –  network element type → workflow
    // ──────────────────────────────────────────────

    public static final Map<String, String> WF_MAP;

    static {
        WF_MAP = new LinkedHashMap<>();
        WF_MAP.put("HLR",      "HLR_Provisioning");
        WF_MAP.put("HSS",      "HLR_Provisioning");
        WF_MAP.put("IMS-Core", "IMS_Registration");
        WF_MAP.put("PCRF",     "APN_Configuration");
        WF_MAP.put("PCF",      "APN_Configuration");
        WF_MAP.put("SMSC",     "Charging_Rule_Setup");
        WF_MAP.put("MSC",      "Mobility_Configuration");
        WF_MAP.put("MME",      "Mobility_Configuration");
        WF_MAP.put("SBC",      "SBC_Configuration");

        WF_MAP.put("PE Router",        "PE_Configuration");
        WF_MAP.put("Route Reflector",  "BGP_Peering");
        WF_MAP.put("VRF Instance",     "VRF_Allocation");
        WF_MAP.put("NMS",              "Monitoring_Setup");

        WF_MAP.put("vCPE",             "CPE_Deployment");
        WF_MAP.put("SD-WAN Controller","Controller_Setup");
        WF_MAP.put("Orchestrator",     "ZTP_Bootstrap");

        WF_MAP.put("OLT",    "ONT_Provisioning");
        WF_MAP.put("BNG",    "IP_Pool_Allocation");
        WF_MAP.put("RADIUS", "AAA_Configuration");
        WF_MAP.put("EMS",    "EMS_Setup");
    }

    // ──────────────────────────────────────────────
    //  BLOCKED_KEYWORDS  –  dangerous CLI commands
    // ──────────────────────────────────────────────

    public static final Set<String> BLOCKED_KEYWORDS = Set.of(
            "erase",
            "reload",
            "format",
            "shutdown",
            "no switchport",
            "write erase",
            "delete startup-config",
            "boot system flash"
    );

    // ──────────────────────────────────────────────
    //  INSTANCE_ATTRS  –  per-instance identifiers
    // ──────────────────────────────────────────────

    public static final Set<String> INSTANCE_ATTRS = Set.of(
            "msisdn",
            "imsi",
            "imei",
            "pe_ip",
            "hostname",
            "serviceid",
            "serial",
            "loopback",
            "management_ip"
    );

    // ──────────────────────────────────────────────
    //  Helpers
    // ──────────────────────────────────────────────

    /**
     * Returns the {@link ServiceResourceDef} for the given service key.
     * Falls back to "mobile" when the key is not found.
     */
    public static ServiceResourceDef get(String svc) {
        if (svc == null) return SERVICE_RESOURCES.get("mobile");
        ServiceResourceDef def = SERVICE_RESOURCES.get(svc.toLowerCase(Locale.ROOT));
        return def != null ? def : SERVICE_RESOURCES.get("mobile");
    }

    // ──────────────────────────────────────────────
    //  seedKbPatterns  –  seed plans per service
    // ──────────────────────────────────────────────

    /**
     * Returns a list of seed-pattern dictionaries used by the PatternEngine
     * to bootstrap the knowledge graph.
     */
    public static List<Map<String, Object>> seedKbPatterns() {
        List<Map<String, Object>> patterns = new ArrayList<>();

        // ── Mobile ──────────────────────────────────────
        patterns.add(seedPattern(
                "mobile",
                List.of("DESIGNED", "FEASIBILITY_CHECKED", "HLR_PROVISIONED",
                        "IMS_REGISTERED", "PCRF_CONFIGURED", "ACTIVE"),
                Map.of(
                        "HLR/HSS",   Map.of("msisdn", "VAR_MSISDN_1", "imsi", "VAR_IMSI_1"),
                        "IMS-Core",  Map.of("volte_enabled", true, "codec_profile", "default"),
                        "PCRF/PCF",  Map.of("apn", "internet", "qos_profile", "gold")
                ),
                List.of("HLR/HSS", "IMS-Core", "PCRF/PCF")
        ));

        // ── L3VPN ───────────────────────────────────────
        patterns.add(seedPattern(
                "l3vpn",
                List.of("DESIGNED", "FEASIBILITY_CHECKED", "RESOURCE_ALLOCATED",
                        "DEVICE_CONFIGURED", "PEERING_ESTABLISHED", "ACTIVE"),
                Map.of(
                        "PE Router",       Map.of("vrf_name", "CUST-A", "rd", "65000:100"),
                        "Route Reflector", Map.of("cluster_id", "1", "asn", 65000),
                        "VRF Instance",    Map.of("vrf_name", "CUST-A", "route_targets", "65000:100")
                ),
                List.of("PE Router", "Route Reflector", "VRF Instance")
        ));

        // ── SD-WAN ──────────────────────────────────────
        patterns.add(seedPattern(
                "sdwan",
                List.of("DESIGNED", "FEASIBILITY_CHECKED", "CPE_DEPLOYED",
                        "TUNNELS_ESTABLISHED", "POLICIES_APPLIED", "ACTIVE"),
                Map.of(
                        "vCPE/uCPE",        Map.of("encryption", "ipsec", "wan_interfaces", "2"),
                        "SD-WAN Controller", Map.of("policy_set", "default", "site_list", "branch-1"),
                        "Orchestrator",      Map.of("ztp_url", "https://ztp.example.com")
                ),
                List.of("vCPE/uCPE", "SD-WAN Controller", "Orchestrator")
        ));

        // ── Broadband ───────────────────────────────────
        patterns.add(seedPattern(
                "broadband",
                List.of("DESIGNED", "FEASIBILITY_CHECKED", "ONT_PROVISIONED",
                        "VLAN_ASSIGNED", "IP_ALLOCATED", "ACTIVE"),
                Map.of(
                        "OLT",      Map.of("ont_model", "ABC-1000", "speed_profile", "100M"),
                        "BNG/BRAS", Map.of("ip_pool", "pool-bb-01", "subscriber_profile", "residential"),
                        "RADIUS",   Map.of("auth_method", "PAP")
                ),
                List.of("OLT", "BNG/BRAS", "RADIUS")
        ));

        return patterns;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> seedPattern(
            String serviceType,
            List<String> workflows,
            Map<String, ?> params,
            List<String> devices) {

        Map<String, Object> pattern = new LinkedHashMap<>();
        pattern.put("workflows", workflows);
        pattern.put("params", params);
        pattern.put("devices", devices);
        pattern.put("service", serviceType);
        return pattern;
    }
}
