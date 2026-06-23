package com.telecom.orchestrator.security;

import java.util.*;
import java.util.regex.*;

public class DataMasker {
    private static final Pattern MSISDN_RE = Pattern.compile("\\+?\\d{5,15}");
    private static final Pattern IP_RE = Pattern.compile("\\b(?:\\d{1,3}\\.){3}\\d{1,3}\\b");

    private final Map<String, String> map = new LinkedHashMap<>();
    private int msisdnCtr = 0;
    private int ipCtr = 0;

    public MaskResult mask(String text) {
        map.clear();
        msisdnCtr = 0;
        ipCtr = 0;

        // Replace MSISDNs
        Matcher msisdnMatcher = MSISDN_RE.matcher(text);
        StringBuffer sb = new StringBuffer();
        while (msisdnMatcher.find()) {
            String val = msisdnMatcher.group();
            String token = map.get(val);
            if (token == null) {
                msisdnCtr++;
                token = "VAR_MSISDN_" + msisdnCtr;
                map.put(token, val);
                map.put(val, token);
            }
            msisdnMatcher.appendReplacement(sb, Matcher.quoteReplacement(token));
        }
        msisdnMatcher.appendTail(sb);
        text = sb.toString();

        // Replace IPs
        Matcher ipMatcher = IP_RE.matcher(text);
        sb = new StringBuffer();
        while (ipMatcher.find()) {
            String val = ipMatcher.group();
            String token = map.get(val);
            if (token == null) {
                ipCtr++;
                token = "VAR_IP_" + ipCtr;
                map.put(token, val);
                map.put(val, token);
            }
            ipMatcher.appendReplacement(sb, Matcher.quoteReplacement(token));
        }
        ipMatcher.appendTail(sb);
        text = sb.toString();

        // Return only VAR_* → real mapping
        Map<String, String> tokenMap = new LinkedHashMap<>();
        for (var e : map.entrySet()) {
            if (e.getKey().startsWith("VAR_")) {
                tokenMap.put(e.getKey(), e.getValue());
            }
        }

        return new MaskResult(text, tokenMap);
    }

    public record MaskResult(String maskedText, Map<String, String> tokenMap) {}
}
