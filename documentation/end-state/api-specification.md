# Telecom Orchestrator — End-State API Specification

> **Version:** 3.0.0 (Production Target)  
> **Standards:** TM Forum Open APIs v4.1.0 (TMF622, TMF641, TMF640, TMF638, TMF639)  
> **Protocol:** HTTPS (TLS 1.3)  
> **Base URL:** `https://orchestrator.yourcompany.com/api`  
> **Content-Type:** `application/json`  
> **Architecture:** Nginx reverse proxy → FastAPI (uvicorn/gunicorn) → Redis (RQ) → Hermes Workers → MCP bridges  

---

## Table of Contents

1. [API Gateway Configuration](#1-api-gateway-configuration)
2. [TMF622 Product Ordering API](#2-tmf622-product-ordering-api)
3. [TMF641 Service Ordering API](#3-tmf641-service-ordering-api)
4. [TMF640 Service Activation API](#4-tmf640-service-activation-api)
5. [TMF638 Service Inventory API](#5-tmf638-service-inventory-api)
6. [TMF639 Resource Inventory API](#6-tmf639-resource-inventory-api)
7. [Internal Orchestrator APIs](#7-internal-orchestrator-apis)
8. [CRM Webhook Specification](#8-crm-webhook-specification)
9. [Authentication & Authorization](#9-authentication--authorization)
10. [Error Handling](#10-error-handling)
11. [Script Call References](#11-script-call-references)

---

## 1. API Gateway Configuration

### 1.1 Nginx Reverse Proxy

All external traffic terminates at Nginx before reaching the FastAPI application. The gateway handles TLS, rate limiting, authentication pre-check, CORS, and request logging.

```
                  ┌──────────────┐
   CRM Clients ──→│   Nginx      │──→ FastAPI (127.0.0.1:8000)
   Port 443       │   Reverse    │
   (TLS 1.3)      │   Proxy      │──→ Health Check (127.0.0.1:8000/health)
                  └──────────────┘
```

**Nginx Configuration (`/etc/nginx/nginx.conf`):**

```nginx
upstream fastapi_backend {
    server 127.0.0.1:8000 max_fails=3 fail_timeout=30s;
    keepalive 32;
}

server {
    listen 443 ssl http2;
    server_name orchestrator.yourcompany.com;

    # TLS 1.3 with strong ciphers
    ssl_protocols TLSv1.3;
    ssl_certificate     /etc/nginx/certs/fullchain.pem;
    ssl_certificate_key /etc/nginx/certs/privkey.pem;
    ssl_ciphers ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # Auth pre-check for all API routes
    location /api/ {
        # API Key or Bearer token validation (if using njs/auth_request)
        auth_request /auth/validate;
        
        proxy_pass http://fastapi_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;
    }

    # Internal auth validation endpoint (FastAPI sub-route)
    location = /auth/validate {
        internal;
        proxy_pass http://fastapi_backend/auth/validate;
        proxy_pass_request_body off;
        proxy_set_header Content-Length "";
        proxy_set_header X-Original-URI $request_uri;
        proxy_set_header X-API-Key $http_x_api_key;
        proxy_set_header Authorization $http_authorization;
    }

    # Redirect HTTP → HTTPS
    error_page 497 =301 https://$host:$server_port$request_uri;
}

server {
    listen 80;
    server_name orchestrator.yourcompany.com;
    return 301 https://$host$request_uri;
}
```

### 1.2 Rate Limiting

Rate limits are enforced at two layers: Nginx (coarse) and FastAPI middleware (fine-grained by role).

| Tier          | Rate Limit (Nginx)      | Burst | Scope             |
|---------------|-------------------------|-------|-------------------|
| CRM systems   | 120 requests/minute     | 20    | Per API key       |
| Internal tools| 300 requests/minute     | 50    | Per IP            |
| Health checks | Unlimited               | —     | `/health`         |

**Nginx rate limiting config snippet:**

```nginx
limit_req_zone $http_x_api_key zone=crm_limit:10m rate=120r/m;
limit_req_zone $binary_remote_addr zone=internal_limit:10m rate=300r/m;

location /api/tmf622/ {
    limit_req zone=crm_limit burst=20 nodelay;
    limit_req_status 429;
    proxy_pass http://fastapi_backend;
}

location /api/ {
    limit_req zone=internal_limit burst=50 nodelay;
    limit_req_status 429;
    proxy_pass http://fastapi_backend;
}

location /health {
    limit_req off;
    proxy_pass http://fastapi_backend;
}
```

### 1.3 TLS Configuration

| Parameter              | Value                                      |
|------------------------|--------------------------------------------|
| Minimum TLS version    | TLS 1.3                                    |
| Certificate            | Let's Encrypt (auto-renew via certbot)      |
| Client certificates    | Optional mTLS for high-security deployments |
| HSTS                   | `max-age=31536000; includeSubDomains`       |
| Cert renewal cron      | `0 3 * * * certbot renew --quiet`           |

### 1.4 CORS Configuration

```json
{
  "allowed_origins": [
    "https://crm.acme-corp.com",
    "https://salesforce.commscloud.com",
    "https://admin.orchestrator.yourcompany.com"
  ],
  "allowed_methods": ["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
  "allowed_headers": ["Authorization", "X-API-Key", "Content-Type", "X-Correlation-ID"],
  "exposed_headers": ["X-Request-ID", "X-RateLimit-Remaining"],
  "max_age": 3600
}
```

---

## 2. TMF622 Product Ordering API

> **Standard:** TM Forum TMF622 Product Ordering Management API v4.1.0  
> **Role:** CRM-facing entry point. Accepts product orders, decomposes into service orders, returns 202 Accepted.  
> **Auth:** API key (X-API-Key header) or OAuth2 Bearer token with scope `write:order`.

### 2.1 POST /api/tmf622/productOrder

Create a product order. The Order Decomposition Engine looks up the product in the catalog, determines the required service templates, and creates one or more child `ServiceOrder` (TMF641) resources. A 202 Accepted response is returned immediately; CRM polls or listens for webhooks.

| Aspect           | Details                                      |
|------------------|----------------------------------------------|
| **Method**       | `POST`                                       |
| **Path**         | `/api/tmf622/productOrder`                   |
| **Content-Type** | `application/json`                           |
| **Response**     | 202 Accepted — `ProductOrder` object         |

**Request Schema:**

| Field                    | Type         | Required | Description                                                           |
|--------------------------|--------------|----------|-----------------------------------------------------------------------|
| `externalId`             | `string`     | Yes      | CRM's order reference. **Idempotency key** — duplicate POST returns 409. |
| `priority`               | `string`     | No       | `"urgent"`, `"standard"` (default), or `"bulk"`                      |
| `category`               | `string`     | No       | High-level category for routing: `"VPN"`, `"Internet"`, `"Voice"`, etc. |
| `channel`                | `object`     | No       | `{ "name": "Salesforce", "type": "CRM" }`                             |
| `relatedParty`           | `array`      | Yes      | At least one `{ "role": "customer", "name": "...", "id": "..." }`     |
| `productOrderItem`       | `array`      | Yes      | One or more product order items (see below)                            |
| `requestedCompletionDate`| `string`     | No       | ISO 8601 timestamp requested by CRM                                   |
| `notificationContact`    | `string`     | No       | Email or Slack channel for operational alerts                          |

**productOrderItem object:**

| Field              | Type     | Required | Description                                            |
|--------------------|----------|----------|--------------------------------------------------------|
| `id`               | `string` | Yes      | Unique item ID within this order (e.g., `"1"`, `"2"`)  |
| `action`           | `string` | Yes      | `"add"`, `"modify"`, `"delete"`, `"noChange"`          |
| `product`          | `object` | Yes      | `{ "id": "prod-l3vpn-01", "name": "Enterprise MPLS L3VPN" }` |
| `productOffering`  | `object` | No       | `{ "id": "offering-l3vpn-100mbps", ... }`              |
| `itemTerm`         | `array`  | No       | `[{ "name": "contractDuration", "value": "36" }]`       |
| `characteristic`   | `array`  | Yes      | Service-defining `[{ "name": "...", "value": "..." }]`  |

**characteristic known values:**

| Name                | Value Examples                    | Description                     |
|---------------------|-----------------------------------|---------------------------------|
| `customerSegment`   | `retail`, `enterprise`, `wholesale`| Customer market segment         |
| `slaTier`           | `gold`, `silver`, `platinum`, `bronze` | SLA tier                 |
| `siteName`          | `San Jose HQ`                     | Site/location name              |
| `siteCode`          | `SJC`                             | Site code                       |
| `bandwidth`         | `100`, `1000`                     | Bandwidth numeric               |
| `bandwidthUnit`     | `Mbps`, `Gbps`                    | Bandwidth unit                  |
| `targetDevice`      | `sfo-pe-01`                       | Target network device           |
| `routingProtocol`   | `BGP`, `OSPF`, `Static`           | Routing protocol                |
| `customerASN`       | `65002`                           | Customer BGP AS number          |
| `wanIPSubnet`       | `auto-allocate`                   | WAN subnet strategy             |
| `callbackUrl`       | `https://crm.acme-corp.com/api/...`| CRM webhook callback URL       |

**Example Request — L3VPN Product Order:**

```json
{
  "externalId": "CRM-ORDER-12345",
  "priority": "standard",
  "category": "VPN",
  "channel": { "name": "Salesforce", "type": "CRM" },
  "relatedParty": [
    { "role": "customer", "name": "Acme Corporation", "id": "CUST-0042" }
  ],
  "productOrderItem": [
    {
      "id": "1",
      "action": "add",
      "product": {
        "id": "prod-l3vpn-01",
        "name": "Enterprise MPLS L3VPN"
      },
      "productOffering": {
        "id": "offering-l3vpn-100mbps",
        "name": "MPLS L3VPN 100 Mbps"
      },
      "itemTerm": [
        { "name": "contractDuration", "value": "36" }
      ],
      "characteristic": [
        { "name": "siteName",        "value": "San Jose HQ" },
        { "name": "siteCode",        "value": "SJC" },
        { "name": "bandwidth",       "value": "100" },
        { "name": "bandwidthUnit",   "value": "Mbps" },
        { "name": "targetDevice",    "value": "sfo-pe-01" },
        { "name": "ceDeviceModel",   "value": "cisco-isr-4461" },
        { "name": "routingProtocol", "value": "BGP" },
        { "name": "customerASN",     "value": "65002" },
        { "name": "wanIPSubnet",     "value": "auto-allocate" },
        { "name": "callbackUrl",     "value": "https://crm.acme-corp.com/api/webhooks/telco-order-status" }
      ]
    }
  ],
  "requestedCompletionDate": "2026-06-22T18:00:00Z"
}
```

**Example Request — Mobile Voice Product Order (Simple):**

```json
{
  "externalId": "CRM-MOBILE-789",
  "priority": "urgent",
  "category": "Voice",
  "relatedParty": [
    { "role": "customer", "name": "Jane Smith", "id": "CUST-1192" }
  ],
  "productOrderItem": [
    {
      "id": "1",
      "action": "add",
      "product": { "id": "prod-mobile-voice-01", "name": "Mobile Voice Gold" },
      "characteristic": [
        { "name": "customerSegment", "value": "retail" },
        { "name": "slaTier", "value": "gold" },
        { "name": "msisdn", "value": "447700123456" },
        { "name": "imsi", "value": "234151234567890" },
        { "name": "volte_enabled", "value": "true" },
        { "name": "codec_profile", "value": "EVS_AMR-WB" },
        { "name": "callbackUrl", "value": "https://crm.acme-corp.com/api/webhooks/telco-order-status" }
      ]
    }
  ]
}
```

**Response — 202 Accepted:**

```json
{
  "id": "ord-20260622-0001",
  "href": "/api/tmf622/productOrder/ord-20260622-0001",
  "state": "acknowledged",
  "externalId": "CRM-ORDER-12345",
  "priority": "standard",
  "category": "VPN",
  "orderDate": "2026-06-22T09:30:00Z",
  "expectedCompletionDate": "2026-06-22T09:35:00Z",
  "requestedCompletionDate": "2026-06-22T18:00:00Z",
  "relatedParty": [
    { "role": "customer", "name": "Acme Corporation", "id": "CUST-0042" }
  ],
  "productOrderItem": [
    {
      "id": "1",
      "action": "add",
      "state": "acknowledged",
      "product": { "id": "prod-l3vpn-01", "name": "Enterprise MPLS L3VPN" }
    }
  ],
  "serviceOrder": [
    {
      "id": "so-l3vpn-0001",
      "href": "/api/tmf641/serviceOrder/so-l3vpn-0001",
      "role": "parent",
      "state": "acknowledged"
    },
    {
      "id": "so-l3vpn-0001-resource",
      "href": "/api/tmf641/serviceOrder/so-l3vpn-0001-resource",
      "role": "child",
      "description": "Resource allocation sub-order",
      "state": "acknowledged"
    }
  ]
}
```

**Error Codes:**

| Status | Code                      | Meaning                                               |
|--------|---------------------------|-------------------------------------------------------|
| 400    | `INVALID_REQUEST`         | Malformed JSON, missing required fields                |
| 401    | `UNAUTHORIZED`            | Missing or invalid API key / OAuth2 token              |
| 403    | `FORBIDDEN`               | Valid credentials but insufficient scope               |
| 404    | `PRODUCT_NOT_FOUND`       | `product.id` not found in product catalog              |
| 409    | `DUPLICATE_ORDER`         | `externalId` already processed (idempotency conflict)  |
| 422    | `VALIDATION_ERROR`        | Business rule violation (e.g., invalid characteristic) |
| 429    | `RATE_LIMIT_EXCEEDED`     | Too many requests; retry after `Retry-After` header    |
| 500    | `INTERNAL_ERROR`          | Unexpected server error                                |
| 503    | `SERVICE_UNAVAILABLE`     | Database/Redis backend unreachable                     |

### 2.2 GET /api/tmf622/productOrder/{id}

Query a product order's current status, including its child service orders.

| Aspect           | Details                                                    |
|------------------|------------------------------------------------------------|
| **Method**       | `GET`                                                      |
| **Path**         | `/api/tmf622/productOrder/{id}`                            |
| **Path Params**  | `id` (string) — Product order ID (e.g., `ord-20260622-0001`)|
| **Response**     | 200 OK — `ProductOrder` object with current state           |

**Response (in-progress):**

```json
{
  "id": "ord-20260622-0001",
  "href": "/api/tmf622/productOrder/ord-20260622-0001",
  "state": "inProgress",
  "externalId": "CRM-ORDER-12345",
  "orderDate": "2026-06-22T09:30:00Z",
  "expectedCompletionDate": "2026-06-22T09:35:00Z",
  "completionDate": null,
  "productOrderItem": [
    {
      "id": "1",
      "action": "add",
      "state": "inProgress",
      "product": { "id": "prod-l3vpn-01", "name": "Enterprise MPLS L3VPN" }
    }
  ],
  "serviceOrder": [
    {
      "id": "so-l3vpn-0001",
      "href": "/api/tmf641/serviceOrder/so-l3vpn-0001",
      "state": "inProgress"
    }
  ]
}
```

**Error Codes:** 401, 403, 404 (`ORDER_NOT_FOUND`), 429, 500, 503.

### 2.3 POST /api/tmf622/productOrder/{id}/cancel

Cancel a product order that has not yet reached `completed` or `failed`.

| Aspect           | Details                                                    |
|------------------|------------------------------------------------------------|
| **Method**       | `POST`                                                     |
| **Path**         | `/api/tmf622/productOrder/{id}/cancel`                     |
| **Path Params**  | `id` (string) — Product order ID                           |
| **Request Body** | `{ "reason": "Customer requested cancellation" }` (optional)|
| **Response**     | 200 OK — Updated `ProductOrder` with `state: "cancelled"`   |

**Error Codes:** 401, 403, 404, 409 (`ORDER_NOT_CANCELLABLE` — already completed/failed), 429, 500.

### 2.4 TMF622 Order State Machine

```
                  ┌─────────────┐
  CRM POSTs ───→  │ acknowledged │
                  └──────┬──────┘
                         │ (decomposed into ServiceOrders)
                  ┌──────▼──────┐
                  │  inProgress  │── Webhook: order.processing
                  └──┬──┬──┬──┬─┘
                     │  │  │  │
              ┌──────┘  │  │  └──────────┐
              │         │  │             │
     ┌────────▼──┐ ┌───▼──▼──┐   ┌──────▼──────┐
     │   held    │ │pending  │   │   completed  │── Webhook: order.completed
     └───────────┘ └────┬────┘   └──────────────┘
                        │
                 ┌──────▼──────┐
                 │  cancelled  │── Webhook: order.cancelled
                 └─────────────┘

  On retry exhaustion:
                 ┌─────────────┐
                 │   failed    │── Webhook: order.failed + Ops alert
                 └─────────────┘
```

| State          | Description                                                            |
|----------------|------------------------------------------------------------------------|
| `acknowledged` | Order received, validated, awaiting decomposition into service orders  |
| `inProgress`   | At least one child service order is being fulfilled                    |
| `pending`      | Awaiting external dependency (e.g., manual approval, field dispatch)   |
| `held`         | Order suspended — resource pool exhausted or manual intervention needed|
| `cancelled`    | Order cancelled by CRM or admin                                        |
| `completed`    | All child service orders completed, service(s) active                  |
| `failed`       | Fulfillment exhausted retries; ops alerted                             |

---

## 3. TMF641 Service Ordering API

> **Standard:** TM Forum TMF641 Service Ordering Management API v4.1.0  
> **Role:** Manage individual service orders. CRM queries status; internal orchestrator creates/updates children.  
> **Auth:** API key (`read:order` / `write:order`) or OAuth2.

### 3.1 POST /api/tmf641/serviceOrder

Create or update a service order. Primarily called internally by the Order Decomposition Engine after a TMF622 ProductOrder is decomposed, but CRM can also create standalone service orders.

| Aspect           | Details                                      |
|------------------|----------------------------------------------|
| **Method**       | `POST`                                       |
| **Path**         | `/api/tmf641/serviceOrder`                   |
| **Content-Type** | `application/json`                           |
| **Response**     | 201 Created — `ServiceOrder` object           |

**Request Schema:**

| Field                      | Type     | Required | Description                                             |
|----------------------------|----------|----------|---------------------------------------------------------|
| `externalId`               | `string` | No       | External reference (CRM order ID)                       |
| `category`                 | `string` | Yes      | Service category: `"mobile"`, `"l3vpn"`, `"sdwan"`, `"broadband"` |
| `action`                   | `string` | Yes      | `"add"`, `"modify"`, `"delete"`, `"noChange"`           |
| `priority`                 | `string` | No       | `"urgent"`, `"standard"` (default), `"bulk"`            |
| `relatedParty`             | `array`  | No       | `[{ "role": "customer", "name": "...", "id": "..." }]`   |
| `productOrderId`           | `string` | No       | Parent product order ID (set by Decomposition Engine)   |
| `parentServiceOrderId`     | `string` | No       | Parent service order ID for child sub-orders            |
| `orderItem`                | `array`  | Yes      | One or more service order items                          |
| `characteristic`           | `array`  | No       | Service-level characteristics `[{ "name": "...", "value": "..." }]` |

**orderItem object:**

| Field       | Type     | Required | Description                                             |
|-------------|----------|----------|---------------------------------------------------------|
| `id`        | `string` | Yes      | Unique item ID within this order                         |
| `action`    | `string` | Yes      | `"add"`, `"modify"`, `"delete"`                          |
| `service`   | `object` | No       | `{ "id": "svc-...", "name": "..." }` (set after creation)|
| `characteristic` | `array` | No   | Item-level characteristics                               |

**Example Request — Broadband Service Order:**

```json
{
  "externalId": "CRM-98765",
  "category": "broadband",
  "action": "add",
  "priority": "standard",
  "orderItem": [
    {
      "id": "1",
      "action": "add",
      "characteristic": [
        { "name": "productId", "value": "prod-ftth-100m" },
        { "name": "customerSegment", "value": "retail" },
        { "name": "slaTier", "value": "silver" },
        { "name": "ont_model", "value": "Huawei-HG8245W5" },
        { "name": "vlan", "value": "100" },
        { "name": "speed_profile", "value": "100M-20M" }
      ]
    }
  ]
}
```

**Response — 201 Created:**

```json
{
  "id": "so-bb-0042",
  "href": "/api/tmf641/serviceOrder/so-bb-0042",
  "state": "acknowledged",
  "externalId": "CRM-98765",
  "category": "broadband",
  "action": "add",
  "priority": "standard",
  "orderDate": "2026-06-22T10:00:00Z",
  "orderItem": [
    {
      "id": "1",
      "action": "add",
      "state": "acknowledged"
    }
  ],
  "auditLog": [
    {
      "date": "2026-06-22T10:00:00Z",
      "state": "acknowledged",
      "message": "Service order created"
    }
  ]
}
```

### 3.2 GET /api/tmf641/serviceOrder/{id}

Query service order details including full audit log, milestones, and related service inventory references.

| Aspect           | Details                                                    |
|------------------|------------------------------------------------------------|
| **Method**       | `GET`                                                      |
| **Path**         | `/api/tmf641/serviceOrder/{id}`                            |
| **Path Params**  | `id` (string) — Service order ID                            |
| **Response**     | 200 OK — `ServiceOrder` with audit log and milestones       |

**Example Response — Completed L3VPN Service Order:**

```json
{
  "id": "so-l3vpn-0001",
  "href": "/api/tmf641/serviceOrder/so-l3vpn-0001",
  "state": "completed",
  "externalId": "CRM-ORDER-12345",
  "category": "l3vpn",
  "action": "add",
  "priority": "standard",
  "productOrderId": "ord-20260622-0001",
  "orderDate": "2026-06-22T09:30:01Z",
  "completionDate": "2026-06-22T09:31:05Z",
  "expectedCompletionDate": "2026-06-22T09:35:00Z",
  "orderItem": [
    {
      "id": "1",
      "action": "add",
      "state": "completed",
      "service": {
        "id": "svc-acme-sjc-l3vpn",
        "href": "/api/tmf638/service/svc-acme-sjc-l3vpn",
        "state": "active"
      }
    }
  ],
  "serviceOrderRelationship": [
    {
      "type": "composedOf",
      "serviceOrder": {
        "id": "so-l3vpn-0001-resource",
        "description": "Resource allocation sub-order",
        "state": "completed"
      }
    }
  ],
  "milestone": [
    {
      "id": "ms-so-l3vpn-0001-DESIGNED",
      "name": "DESIGNED",
      "description": "State transition: DESIGNED",
      "milestoneDate": "2026-06-22T09:30:02Z",
      "status": "achieved"
    },
    {
      "id": "ms-so-l3vpn-0001-FEASIBILITY_CHECKED",
      "name": "FEASIBILITY_CHECKED",
      "description": "State transition: FEASIBILITY_CHECKED",
      "milestoneDate": "2026-06-22T09:30:05Z",
      "status": "achieved"
    },
    {
      "id": "ms-so-l3vpn-0001-RESOURCE_ALLOCATED",
      "name": "RESOURCE_ALLOCATED",
      "description": "State transition: RESOURCE_ALLOCATED",
      "milestoneDate": "2026-06-22T09:30:12Z",
      "status": "achieved"
    },
    {
      "id": "ms-so-l3vpn-0001-DEVICE_CONFIGURED",
      "name": "DEVICE_CONFIGURED",
      "description": "State transition: DEVICE_CONFIGURED",
      "milestoneDate": "2026-06-22T09:30:45Z",
      "status": "achieved"
    },
    {
      "id": "ms-so-l3vpn-0001-PEERING_ESTABLISHED",
      "name": "PEERING_ESTABLISHED",
      "description": "State transition: PEERING_ESTABLISHED",
      "milestoneDate": "2026-06-22T09:31:02Z",
      "status": "achieved"
    }
  ],
  "auditLog": [
    { "date": "2026-06-22T09:30:01Z", "state": "acknowledged", "message": "Order received, queued for fulfillment" },
    { "date": "2026-06-22T09:30:05Z", "state": "inProgress", "message": "Feasibility check on sfo-pe-01: PASS" },
    { "date": "2026-06-22T09:30:12Z", "state": "inProgress", "message": "Resources allocated: VRF=CUST-SJC-CORP, RD=65001:1001" },
    { "date": "2026-06-22T09:30:45Z", "state": "inProgress", "message": "Configuration pushed to sfo-pe-01 (18 lines)" },
    { "date": "2026-06-22T09:31:02Z", "state": "inProgress", "message": "Verification: BGP Established, 12 prefixes received, ping OK" },
    { "date": "2026-06-22T09:31:05Z", "state": "completed", "message": "Service ACTIVE. Resources: VRF x1, BGP x1, Subnet x1, IF x1" }
  ]
}
```

**Error Codes:** 401, 403, 404 (`ORDER_NOT_FOUND`), 429, 500.

### 3.3 POST /api/tmf641/serviceOrder/{id}/cancel

Cancel a service order that is not yet `completed`.

| Aspect           | Details                                                    |
|------------------|------------------------------------------------------------|
| **Method**       | `POST`                                                     |
| **Path**         | `/api/tmf641/serviceOrder/{id}/cancel`                     |
| **Path Params**  | `id` (string) — Service order ID                            |
| **Request Body** | `{ "reason": "..." }` (optional)                            |
| **Response**     | 200 OK — `ServiceOrder` with `state: "cancelled"`           |

**Error Codes:** 401, 403, 404, 409 (`ORDER_NOT_CANCELLABLE`), 429, 500.

### 3.4 TMF641 State Machine & Milestone Events

The service order inherits the TMF622 state machine (acknowledged → inProgress → completed/failed/cancelled). Additionally, it emits **TMF641 Milestone Events** for each KB-defined lifecycle state.

| Service Type | Lifecycle Milestones                                                                               |
|-------------|----------------------------------------------------------------------------------------------------|
| `mobile`    | DESIGNED → FEASIBILITY_CHECKED → HLR_PROVISIONED → IMS_REGISTERED → PCRF_CONFIGURED → ACTIVE      |
| `l3vpn`     | DESIGNED → FEASIBILITY_CHECKED → RESOURCE_ALLOCATED → DEVICE_CONFIGURED → PEERING_ESTABLISHED → ACTIVE |
| `sdwan`     | DESIGNED → FEASIBILITY_CHECKED → CPE_DEPLOYED → TUNNELS_ESTABLISHED → POLICIES_APPLIED → ACTIVE    |
| `broadband` | DESIGNED → FEASIBILITY_CHECKED → ONT_PROVISIONED → VLAN_ASSIGNED → IP_ALLOCATED → ACTIVE           |

Each milestone event is a `ServiceOrderMilestoneEvent` (TMF641 §notification). The final ACTIVE state emits a `ServiceOrderStateChangeEvent`.

---

## 4. TMF640 Service Activation API

> **Standard:** TM Forum TMF640 Service Activation and Configuration API v4.1.0  
> **Role:** Directly activate, query, modify, or deactivate a service configuration on the network.  
> **Auth:** API key (`write:order`) or OAuth2.  
> **Note:** In the PoC, TMF640 requests are accepted via `POST /api/process` with a structured JSON body. In the production system, they are first-class REST endpoints.

### 4.1 POST /api/tmf640/service

Activate a service configuration. Creates a new service instance or transitions an existing one to ACTIVE state.

| Aspect           | Details                                      |
|------------------|----------------------------------------------|
| **Method**       | `POST`                                       |
| **Path**         | `/api/tmf640/service`                        |
| **Content-Type** | `application/json`                           |
| **Response**     | 201 Created — `Service` object                |

**Request Schema:**

| Field            | Type     | Required | Description                                              |
|------------------|----------|----------|----------------------------------------------------------|
| `serviceId`      | `string` | No       | External service ID (MSISDN, circuit ID); auto-generated if absent |
| `action`         | `string` | Yes      | `"activate"`, `"deactivate"`, `"modify"`                  |
| `category`       | `string` | No       | `"mobile"`, `"l3vpn"`, `"sdwan"`, `"broadband"`          |
| `characteristic` | `array`  | Yes      | `[{ "name": "customerSegment", "value": "retail" }, ...]`  |

**Example Request — Activate Mobile Voice (Gold):**

```json
{
  "serviceId": "MSISDN-447700123456",
  "action": "activate",
  "category": "mobile",
  "characteristic": [
    { "name": "customerSegment", "value": "retail" },
    { "name": "slaTier", "value": "gold" },
    { "name": "productId", "value": "mobile-voice" },
    { "name": "msisdn", "value": "447700123456" },
    { "name": "imsi", "value": "234151234567890" },
    { "name": "subscriber_profile", "value": "Gold_VoLTE_IntlRoam" },
    { "name": "roaming_profile", "value": "WorldZone1" },
    { "name": "volte_enabled", "value": "true" },
    { "name": "codec_profile", "value": "EVS_AMR-WB" },
    { "name": "apn", "value": "ims.gold.mnc015.mcc234.gprs" },
    { "name": "qos_profile", "value": "QCI-1_VoLTE" },
    { "name": "charging_rule", "value": "Gold_Postpaid_VoLTE" },
    { "name": "bandwidth_limit", "value": "unlimited" }
  ]
}
```

**Response — 201 Created:**

```json
{
  "id": "svc-mobile-00042",
  "href": "/api/tmf640/service/svc-mobile-00042",
  "serviceId": "MSISDN-447700123456",
  "state": "provisioning",
  "category": "mobile",
  "action": "activate",
  "characteristic": [
    { "name": "customerSegment", "value": "retail" },
    { "name": "slaTier", "value": "gold" }
  ],
  "orderDate": "2026-06-22T10:15:00Z",
  "expectedCompletionDate": "2026-06-22T10:16:00Z"
}
```

**Error Codes:** 400 (`INVALID_REQUEST`), 401, 403, 409 (`SERVICE_ALREADY_ACTIVE`), 422 (`VALIDATION_ERROR`), 429, 500, 503.

### 4.2 GET /api/tmf640/service/{id}

Query a service's current state and configuration.

| Aspect           | Details                                      |
|------------------|----------------------------------------------|
| **Method**       | `GET`                                        |
| **Path**         | `/api/tmf640/service/{id}`                   |
| **Path Params**  | `id` (string) — Service ID                    |
| **Response**     | 200 OK — `Service` object                     |

**Example Response:**

```json
{
  "id": "svc-mobile-00042",
  "href": "/api/tmf640/service/svc-mobile-00042",
  "serviceId": "MSISDN-447700123456",
  "state": "active",
  "category": "mobile",
  "characteristic": [
    { "name": "customerSegment", "value": "retail" },
    { "name": "slaTier", "value": "gold" },
    { "name": "msisdn", "value": "447700123456" },
    { "name": "imsi", "value": "234151234567890" },
    { "name": "subscriber_profile", "value": "Gold_VoLTE_IntlRoam" }
  ],
  "relatedService": [
    { "id": "svc-acme-sjc-l3vpn", "href": "/api/tmf638/service/svc-acme-sjc-l3vpn", "relationshipType": "dependsOn" }
  ],
  "startDate": "2026-06-22T10:15:45Z",
  "completionDate": "2026-06-22T10:16:00Z",
  "stateChangeDate": "2026-06-22T10:16:00Z"
}
```

**Error Codes:** 401, 403, 404 (`SERVICE_NOT_FOUND`), 429, 500.

### 4.3 PATCH /api/tmf640/service/{id}

Modify an existing service configuration. Partial update — only changed characteristics need to be sent.

| Aspect           | Details                                      |
|------------------|----------------------------------------------|
| **Method**       | `PATCH`                                      |
| **Path**         | `/api/tmf640/service/{id}`                   |
| **Path Params**  | `id` (string) — Service ID                    |
| **Content-Type** | `application/json`                           |
| **Response**     | 200 OK — Updated `Service` object             |

**Example Request — Upgrade bandwidth on L3VPN:**

```json
{
  "action": "modify",
  "characteristic": [
    { "name": "bandwidth", "value": "1000" },
    { "name": "qos_profile", "value": "QCI-3_Premium" }
  ]
}
```

**Error Codes:** 400, 401, 403, 404, 409 (`SERVICE_NOT_MODIFIABLE` — in terminal state), 422, 429, 500.

### 4.4 DELETE /api/tmf640/service/{id}

Deactivate a service. Transitions the service from ACTIVE to TERMINATED.

| Aspect           | Details                                      |
|------------------|----------------------------------------------|
| **Method**       | `DELETE`                                     |
| **Path**         | `/api/tmf640/service/{id}`                   |
| **Path Params**  | `id` (string) — Service ID                    |
| **Response**     | 200 OK — `Service` with `state: "terminated"` |

**Example Request:**

```bash
curl -X DELETE https://orchestrator.yourcompany.com/api/tmf640/service/svc-mobile-00042 \
  -H "X-API-Key: rm1_abc123..."
```

**Example Response:**

```json
{
  "id": "svc-mobile-00042",
  "href": "/api/tmf640/service/svc-mobile-00042",
  "state": "terminated",
  "serviceId": "MSISDN-447700123456",
  "terminationDate": "2026-06-22T12:00:00Z"
}
```

**Error Codes:** 401, 403, 404, 409 (`SERVICE_NOT_TERMINABLE`), 429, 500.

---

## 5. TMF638 Service Inventory API

> **Standard:** TM Forum TMF638 Service Inventory Management API v4.1.0  
> **Role:** Read-only inventory of all active and historical services. Searchable, filterable.  
> **Auth:** API key (`read:order`) or OAuth2.

### 5.1 GET /api/tmf638/service

List all services with optional filtering.

| Aspect           | Details                                      |
|------------------|----------------------------------------------|
| **Method**       | `GET`                                        |
| **Path**         | `/api/tmf638/service`                        |
| **Query Params** | `?state=active&category=mobile&customerId=CUST-0042&offset=0&limit=50` |
| **Response**     | 200 OK — Paginated list of `Service` objects  |

**Query Parameters:**

| Param       | Type     | Required | Description                                        |
|-------------|----------|----------|----------------------------------------------------|
| `state`     | `string` | No       | Filter: `active`, `suspended`, `terminated`, `all` |
| `category`  | `string` | No       | Filter: `mobile`, `l3vpn`, `sdwan`, `broadband`    |
| `customerId`| `string` | No       | Filter by customer ID                               |
| `offset`    | `integer`| No       | Pagination offset (default: 0)                      |
| `limit`     | `integer`| No       | Page size (default: 50, max: 200)                   |

**Example Request:**

```bash
curl "https://orchestrator.yourcompany.com/api/tmf638/service?state=active&category=mobile&limit=10" \
  -H "X-API-Key: rm1_abc123..."
```

**Example Response:**

```json
{
  "totalResults": 1423,
  "offset": 0,
  "limit": 10,
  "service": [
    {
      "id": "svc-mobile-00042",
      "href": "/api/tmf638/service/svc-mobile-00042",
      "serviceId": "MSISDN-447700123456",
      "state": "active",
      "category": "mobile",
      "customerId": "CUST-1192",
      "name": "Mobile Voice Gold — 447700123456",
      "startDate": "2026-06-22T10:16:00Z",
      "lastModified": "2026-06-22T10:16:00Z"
    },
    {
      "id": "svc-mobile-00043",
      "href": "/api/tmf638/service/svc-mobile-00043",
      "serviceId": "MSISDN-447700654321",
      "state": "active",
      "category": "mobile",
      "customerId": "CUST-0042",
      "name": "Mobile Data Platinum — 447700654321",
      "startDate": "2026-06-22T10:20:00Z",
      "lastModified": "2026-06-22T10:20:00Z"
    }
  ]
}
```

**Error Codes:** 401, 403, 400 (`INVALID_FILTER`), 429, 500.

### 5.2 GET /api/tmf638/service/{id}

Get full service details including associated resources.

| Aspect           | Details                                      |
|------------------|----------------------------------------------|
| **Method**       | `GET`                                        |
| **Path**         | `/api/tmf638/service/{id}`                   |
| **Path Params**  | `id` (string) — Service ID                    |
| **Response**     | 200 OK — Full `Service` with resources         |

**Example Response:**

```json
{
  "id": "svc-acme-sjc-l3vpn",
  "href": "/api/tmf638/service/svc-acme-sjc-l3vpn",
  "serviceId": "CIRCUIT-ACME-SJC-001",
  "state": "active",
  "category": "l3vpn",
  "customerId": "CUST-0042",
  "name": "Acme Corp — San Jose MPLS L3VPN",
  "characteristic": [
    { "name": "siteName", "value": "San Jose HQ" },
    { "name": "bandwidth", "value": "100" },
    { "name": "bandwidthUnit", "value": "Mbps" },
    { "name": "routingProtocol", "value": "BGP" }
  ],
  "resource": [
    {
      "id": "res-vrf-001",
      "href": "/api/tmf639/resource/res-vrf-001",
      "type": "VRF Instance",
      "name": "CUST-SJC-CORP",
      "state": "in_service"
    },
    {
      "id": "res-bgp-001",
      "href": "/api/tmf639/resource/res-bgp-001",
      "type": "BGP Peer",
      "name": "BGP-to-CE-10.1.0.2",
      "state": "in_service"
    },
    {
      "id": "res-subnet-001",
      "href": "/api/tmf639/resource/res-subnet-001",
      "type": "IP Subnet",
      "name": "10.1.0.0/30",
      "state": "in_service"
    }
  ],
  "relatedParty": [
    { "role": "customer", "name": "Acme Corporation", "id": "CUST-0042" }
  ],
  "startDate": "2026-06-22T09:31:05Z",
  "lastModified": "2026-06-22T09:31:05Z"
}
```

**Error Codes:** 401, 403, 404, 429, 500.

---

## 6. TMF639 Resource Inventory API

> **Standard:** TM Forum TMF639 Resource Inventory Management API v4.1.0  
> **Role:** Read-only inventory of all logical and physical resources (VRFs, BGP peers, IP subnets, VLANs, VNFs, etc.).  
> **Auth:** API key (`read:order`) or OAuth2.

### 6.1 GET /api/tmf639/resource

List all resources with optional filtering.

| Aspect           | Details                                      |
|------------------|----------------------------------------------|
| **Method**       | `GET`                                        |
| **Path**         | `/api/tmf639/resource`                       |
| **Query Params** | `?resourceType=VRF&deviceName=sfo-pe-01&state=in_service&offset=0&limit=50` |
| **Response**     | 200 OK — Paginated list of `Resource` objects  |

**Query Parameters:**

| Param          | Type     | Required | Description                                         |
|----------------|----------|----------|-----------------------------------------------------|
| `resourceType` | `string` | No       | Filter: `VRF`, `BGP_PEER`, `IP_SUBNET`, `INTERFACE`, `VLAN`, `VNF` |
| `deviceName`   | `string` | No       | Filter by device (`sfo-pe-01`)                      |
| `serviceId`    | `string` | No       | Filter by parent service ID                          |
| `state`        | `string` | No       | Filter: `planned`, `allocated`, `in_service`, `decommissioned` |
| `offset`       | `integer`| No       | Pagination offset (default: 0)                       |
| `limit`        | `integer`| No       | Page size (default: 50, max: 200)                    |

**Example Response:**

```json
{
  "totalResults": 42,
  "offset": 0,
  "limit": 10,
  "resource": [
    {
      "id": "res-vrf-001",
      "href": "/api/tmf639/resource/res-vrf-001",
      "resourceType": "VRF Instance",
      "name": "CUST-SJC-CORP",
      "deviceName": "sfo-pe-01",
      "deviceVendor": "Cisco",
      "state": "in_service",
      "serviceId": "svc-acme-sjc-l3vpn",
      "createdAt": "2026-06-22T09:30:12Z"
    },
    {
      "id": "res-vrf-002",
      "href": "/api/tmf639/resource/res-vrf-002",
      "resourceType": "VRF Instance",
      "name": "CUST-LON-DC-VRF",
      "deviceName": "lon-pe-03",
      "deviceVendor": "Juniper",
      "state": "in_service",
      "serviceId": "svc-acme-lon-l3vpn",
      "createdAt": "2026-06-22T08:15:30Z"
    }
  ]
}
```

**Error Codes:** 401, 403, 400 (`INVALID_FILTER`), 429, 500.

### 6.2 GET /api/tmf639/resource/{id}

Get full resource details including applied configuration and parent service.

| Aspect           | Details                                      |
|------------------|----------------------------------------------|
| **Method**       | `GET`                                        |
| **Path**         | `/api/tmf639/resource/{id}`                  |
| **Path Params**  | `id` (string) — Resource ID                   |
| **Response**     | 200 OK — Full `Resource` object                |

**Example Response:**

```json
{
  "id": "res-vrf-001",
  "href": "/api/tmf639/resource/res-vrf-001",
  "resourceType": "VRF Instance",
  "name": "CUST-SJC-CORP",
  "deviceName": "sfo-pe-01",
  "deviceVendor": "Cisco",
  "deviceModel": "cisco-asr-9006",
  "deviceOsVersion": "IOS-XR 7.9.2",
  "state": "in_service",
  "serviceId": "svc-acme-sjc-l3vpn",
  "parentResourceId": null,
  "config": {
    "vrf_name": "CUST-SJC-CORP",
    "rd": "65001:1001",
    "rt_import": "65001:100",
    "rt_export": "65001:100",
    "route_targets": ["65001:100", "65001:200"],
    "interfaces": ["Gi0/0/1", "Gi0/0/2"]
  },
  "characteristic": [
    { "name": "rd", "value": "65001:1001" },
    { "name": "rt_import", "value": "65001:100" },
    { "name": "rt_export", "value": "65001:100" }
  ],
  "createdAt": "2026-06-22T09:30:12Z",
  "lastModified": "2026-06-22T09:30:12Z"
}
```

**Error Codes:** 401, 403, 404, 429, 500.

---

## 7. Internal Orchestrator APIs

> **Role:** Management, monitoring, and debugging endpoints. Not CRM-facing.  
> **Auth:** API key (admin/operator scope) or internal service account.

### 7.1 GET /api/patterns

List all learned orchestration patterns with confidence and metadata.

| Aspect           | Details                                              |
|------------------|------------------------------------------------------|
| **Method**       | `GET`                                                |
| **Path**         | `/api/patterns`                                      |
| **Response**     | `{ "patterns": [...] }`                               |

**Pattern metadata object:**

| Field           | Type     | Description                                           |
|-----------------|----------|-------------------------------------------------------|
| `id`            | `string` | Pattern ID (e.g., `pat:mobile:a1b2c3d4`)              |
| `service_type`  | `string` | `mobile`, `l3vpn`, `sdwan`, `broadband`               |
| `label`         | `string` | Human-readable description                             |
| `confidence`    | `float`  | 0.0–1.0 (auto-learned patterns grow with usage)       |
| `use_count`     | `int`    | Number of times pattern has been applied               |
| `triples_count` | `int`    | Number of RDF triples in pattern                       |
| `source`        | `string` | `auto` (learned), `teach` (manual), `kb` (KB seed)     |
| `last_used`     | `string` | ISO 8601 timestamp                                     |

**Example Response:**

```json
{
  "patterns": [
    {
      "id": "pat:mobile:a1b2c3d4e5f6",
      "service_type": "mobile",
      "label": "mobile | retail/gold",
      "confidence": 0.85,
      "use_count": 12,
      "triples_count": 42,
      "source": "auto",
      "last_used": "2026-06-22T12:05:00Z"
    },
    {
      "id": "pat:l3vpn:7f8e9d0c1b2a",
      "service_type": "l3vpn",
      "label": "l3vpn | enterprise/platinum",
      "confidence": 0.75,
      "use_count": 8,
      "triples_count": 28,
      "source": "auto",
      "last_used": "2026-06-22T09:31:05Z"
    }
  ]
}
```

### 7.2 POST /api/patterns/teach

Manually inject a pattern via RDF triples. High initial confidence (0.9).

| Aspect           | Details                                              |
|------------------|------------------------------------------------------|
| **Method**       | `POST`                                               |
| **Path**         | `/api/patterns/teach`                                |
| **Content-Type** | `application/json`                                   |
| **Request Body** | `{ "triples": [["subject", "predicate", "object"], ...] }` |
| **Response**     | `{ "status": "learned", "pattern": {...} }`           |

**Example Request:**

```json
{
  "triples": [
    ["my-new-pattern", "rdf:type", "service:MobileVoice"],
    ["my-new-pattern", "orch:hasSegment", "enterprise"],
    ["my-new-pattern", "orch:hasSLA", "gold"],
    ["my-new-pattern", "orch:requiresResource", "res:HLR"],
    ["res:HLR", "orch:provisionedBy", "wf:HLR_Provisioning"],
    ["res:HLR", "orch:hasAttribute", "subscriber_profile=Enterprise_Gold_VoLTE"]
  ]
}
```

**Example Response:**

```json
{
  "status": "learned",
  "pattern": {
    "id": "pat:taught:a1b2c3d4e5f6",
    "service_type": "mobile",
    "label": "mobile | Segment=enterprise / SLA=gold",
    "characteristics": {
      "Segment": "enterprise",
      "SLA": "gold"
    },
    "triples": [
      ["pat:taught:a1b2c3d4e5f6", "rdf:type", "service:MobileVoice"],
      ["pat:taught:a1b2c3d4e5f6", "orch:hasSegment", "enterprise"],
      ["pat:taught:a1b2c3d4e5f6", "orch:hasSLA", "gold"],
      ["pat:taught:a1b2c3d4e5f6", "orch:requiresResource", "res:HLR"],
      ["res:HLR", "orch:provisionedBy", "wf:HLR_Provisioning"],
      ["res:HLR", "orch:hasAttribute", "subscriber_profile=Enterprise_Gold_VoLTE"]
    ],
    "resources": [
      {
        "name": "HLR",
        "workflow": "HLR_Provisioning",
        "attributes": { "subscriber_profile": "Enterprise_Gold_VoLTE" }
      }
    ],
    "confidence": 0.9,
    "use_count": 0,
    "source": "teach",
    "created_at": "2026-06-22T12:10:00Z",
    "last_used": "2026-06-22T12:10:00Z"
  }
}
```

**Error Codes:** 400 (missing `triples`, or triples not an array), 401, 403, 500.

### 7.3 GET /api/patterns/{id}

Get full pattern details including RDF triples and resource definitions.

| Aspect           | Details                                              |
|------------------|------------------------------------------------------|
| **Method**       | `GET`                                                |
| **Path**         | `/api/patterns/{pattern_id}`                         |
| **Path Params**  | `pattern_id` (string) — Pattern ID                   |
| **Response**     | Full `PatternNode.to_dict()` object                   |

**Example Response:**

```json
{
  "id": "pat:mobile:a1b2c3d4e5f6",
  "service_type": "mobile",
  "label": "mobile | retail/gold",
  "characteristics": {
    "customerSegment": "retail",
    "slaTier": "gold",
    "productId": "mobile-voice"
  },
  "triples": [
    ["pat:mobile:a1b2c3d4e5f6", "rdf:type", "service:MobileVoice"],
    ["pat:mobile:a1b2c3d4e5f6", "orch:hascustomerSegment", "retail"],
    ["pat:mobile:a1b2c3d4e5f6", "orch:hasslaTier", "gold"],
    ["pat:mobile:a1b2c3d4e5f6", "orch:requiresResource", "res:HLR-HSS"],
    ["res:HLR-HSS", "orch:provisionedBy", "wf:HLR_Provisioning"],
    ["res:HLR-HSS", "orch:hasAttribute", "msisdn=447700123456"]
  ],
  "resources": [
    {
      "name": "HLR-HSS",
      "workflow": "HLR_Provisioning",
      "role": "Subscriber registry",
      "attributes": {
        "msisdn": "447700123456",
        "imsi": "234151234567890",
        "subscriber_profile": "Gold_VoLTE_IntlRoam"
      }
    }
  ],
  "confidence": 0.85,
  "use_count": 12,
  "created_at": "2026-06-20T10:00:00Z",
  "last_used": "2026-06-22T12:05:00Z",
  "source": "auto"
}
```

**Error Codes:** 401, 403, 404 (`PATTERN_NOT_FOUND`), 500.

### 7.4 GET /api/subscribers/{id}

Get the full subscriber service model, including all provisioned network elements and their current state.

| Aspect           | Details                                              |
|------------------|------------------------------------------------------|
| **Method**       | `GET`                                                |
| **Path**         | `/api/subscribers/{subscriberId}`                    |
| **Path Params**  | `subscriberId` (string) — e.g., `MSISDN-447700123456`|
| **Response**     | `SubscriberModel` object                              |

**SubscriberModel fields:**

| Field              | Type        | Description                                        |
|--------------------|-------------|----------------------------------------------------|
| `subscriberId`     | `string`    | Stable subscriber identifier                        |
| `serviceId`        | `string`    | Current service ID                                  |
| `serviceType`      | `string`    | `mobile`, `l3vpn`, `sdwan`, `broadband`             |
| `state`            | `string`    | `ACTIVE`, `SUSPENDED`, `TERMINATED`                  |
| `version`          | `int`       | Monotonic model version                             |
| `characteristics`  | `object`    | Key-value service characteristics                   |
| `networkElements`  | `array`     | Array of provisioned NE objects                     |
| `createdAt`        | `string`    | ISO 8601                                            |
| `updatedAt`        | `string`    | ISO 8601                                            |

**networkElement object:**

| Field        | Type     | Description                                      |
|--------------|----------|--------------------------------------------------|
| `name`       | `string` | NE name (e.g., `HLR-HSS`, `PCRF-PCF`)            |
| `type`       | `string` | NE type from KB (e.g., `HLR/HSS`)                 |
| `workflow`   | `string` | Workflow that provisioned this NE                 |
| `role`       | `string` | Role description                                  |
| `attributes` | `object` | Key-value attribute map                           |

**Example Response:**

```json
{
  "subscriberId": "MSISDN-447700123456",
  "serviceId": "svc-mobile-00042",
  "serviceType": "mobile",
  "state": "ACTIVE",
  "version": 3,
  "characteristics": {
    "customerSegment": "retail",
    "slaTier": "gold",
    "productId": "mobile-voice",
    "msisdn": "447700123456",
    "imsi": "234151234567890",
    "subscriber_profile": "Gold_VoLTE_IntlRoam",
    "roaming_profile": "WorldZone1",
    "volte_enabled": "true",
    "codec_profile": "EVS_AMR-WB"
  },
  "networkElements": [
    {
      "name": "HLR-HSS",
      "type": "HLR/HSS",
      "workflow": "HLR_Provisioning",
      "role": "Subscriber registry",
      "attributes": {
        "msisdn": "447700123456",
        "imsi": "234151234567890",
        "subscriber_profile": "Gold_VoLTE_IntlRoam",
        "roaming_profile": "WorldZone1",
        "status": "Configured"
      }
    },
    {
      "name": "IMS-Core",
      "type": "IMS-Core",
      "workflow": "IMS_Registration",
      "role": "VoLTE/VoWiFi call control",
      "attributes": {
        "msisdn": "447700123456",
        "volte_enabled": "true",
        "codec_profile": "EVS_AMR-WB",
        "status": "Configured"
      }
    }
  ],
  "createdAt": "2026-06-22T10:16:00Z",
  "updatedAt": "2026-06-22T10:16:00Z"
}
```

**Error Codes:** 401, 403, 404 (`SUBSCRIBER_NOT_FOUND`), 500.

### 7.5 GET /api/subscribers/{id}/diff

Get the change history/diff for a subscriber service model. Shows what changed between the current model and the previous version.

| Aspect           | Details                                              |
|------------------|------------------------------------------------------|
| **Method**       | `GET`                                                |
| **Path**         | `/api/subscribers/{id}/diff`                         |
| **Path Params**  | `id` (string) — Subscriber ID                         |
| **Response**     | `SubscriberDiff` object                               |

**SubscriberDiff fields:**

| Field                | Type      | Description                                           |
|----------------------|-----------|-------------------------------------------------------|
| `hasPrevious`        | `boolean` | Whether a previous model exists                        |
| `isFirstRun`         | `boolean` | `true` if first provisioning for this subscriber       |
| `hasChanges`         | `boolean` | Whether any attributes changed                         |
| `changedAttributes`  | `object`  | `{ "key": { "from": "old", "to": "new" } }`            |
| `networkElementDiffs`| `object`  | `{ "NE_NAME": { "attr": { "from": "old", "to": "new" } } }` |

**Example Response:**

```json
{
  "hasPrevious": true,
  "isFirstRun": false,
  "hasChanges": true,
  "changedAttributes": {
    "slaTier": { "from": "silver", "to": "gold" },
    "bandwidth_limit": { "from": "100Mbps", "to": "unlimited" }
  },
  "networkElementDiffs": {
    "HLR-HSS": {
      "roaming_profile": { "from": "Domestic", "to": "WorldZone1" }
    },
    "PCRF-PCF": {
      "qos_profile": { "from": "QCI-9_BestEffort", "to": "QCI-1_VoLTE" }
    }
  }
}
```

**Error Codes:** 401, 403, 404, 500.

### 7.6 POST /api/locks/release

Admin endpoint to force-release a subscriber lock. Used when a worker crashes and leaves a stale lock.

| Aspect           | Details                                              |
|------------------|------------------------------------------------------|
| **Method**       | `POST`                                               |
| **Path**         | `/api/locks/release`                                 |
| **Content-Type** | `application/json`                                   |
| **Request Body** | `{ "subscriberId": "MSISDN-447700123456" }`          |
| **Response**     | `{ "status": "released", "subscriberId": "..." }`     |

**Error Codes:** 400 (missing `subscriberId`), 401, 403, 500.

### 7.7 GET /api/locks/status

List all active subscriber locks.

| Aspect           | Details                                              |
|------------------|------------------------------------------------------|
| **Method**       | `GET`                                                |
| **Path**         | `/api/locks/status`                                  |
| **Response**     | `{ "activeLocks": N, "locks": [...] }`                |

**Lock object:**

| Field          | Type     | Description                                      |
|----------------|----------|--------------------------------------------------|
| `key`          | `string` | Cache key (`lock:sub:{subscriberId}`)            |
| `subscriberId` | `string` | Subscriber ID                                    |
| `workerId`     | `string` | Order ID holding the lock                         |
| `acquiredAt`   | `number` | Unix timestamp when lock was acquired             |
| `ageSeconds`   | `number` | Seconds since lock acquisition                    |

Locks auto-expire after 30 seconds to prevent deadlock if a worker crashes.

**Example Response:**

```json
{
  "activeLocks": 2,
  "locks": [
    {
      "key": "lock:sub:MSISDN-447700123456",
      "subscriberId": "MSISDN-447700123456",
      "workerId": "PO-A1B2C3D4",
      "acquiredAt": 1749153600.123,
      "ageSeconds": 5.2
    },
    {
      "key": "lock:sub:CIRCUIT-ACME-SJC-001",
      "subscriberId": "CIRCUIT-ACME-SJC-001",
      "workerId": "PO-F9E8D7C6",
      "acquiredAt": 1749153610.456,
      "ageSeconds": 0.9
    }
  ]
}
```

### 7.8 GET /api/notifications/{orderId}

Retrieve all TMF641 lifecycle notifications emitted for a completed order.

| Aspect           | Details                                              |
|------------------|------------------------------------------------------|
| **Method**       | `GET`                                                |
| **Path**         | `/api/notifications/{orderId}`                       |
| **Path Params**  | `orderId` (string) — Order ID                         |
| **Response**     | `{ "orderId": "...", "notifications": [...], "count": N }` |

**Still-processing response:** `{ "notifications": [], "message": "Pipeline still processing" }` (200)

**Completed Example:**

```json
{
  "orderId": "PO-A1B2C3D4",
  "notifications": [
    {
      "eventId": "evt-PO-A1B2C3D4-DESIGNED",
      "eventTime": "2026-06-22T12:00:01Z",
      "eventType": "ServiceOrderMilestoneEvent",
      "correlationId": "corr-PO-A1B2C3D4",
      "domain": "ServiceFulfillment",
      "priority": "normal",
      "event": {
        "serviceOrder": {
          "id": "PO-A1B2C3D4",
          "href": "/api/tmf641/serviceOrder/PO-A1B2C3D4",
          "state": "inProgress",
          "category": "mobile",
          "milestone": [
            {
              "id": "ms-PO-A1B2C3D4-DESIGNED",
              "name": "DESIGNED",
              "status": "achieved",
              "milestoneDate": "2026-06-22T12:00:01Z"
            }
          ]
        }
      }
    },
    {
      "eventId": "evt-PO-A1B2C3D4-ACTIVE",
      "eventTime": "2026-06-22T12:00:45Z",
      "eventType": "ServiceOrderStateChangeEvent",
      "correlationId": "corr-PO-A1B2C3D4",
      "domain": "ServiceFulfillment",
      "priority": "normal",
      "event": {
        "serviceOrder": {
          "id": "PO-A1B2C3D4",
          "href": "/api/tmf641/serviceOrder/PO-A1B2C3D4",
          "state": "completed",
          "category": "mobile",
          "completionDate": "2026-06-22T12:00:45Z"
        }
      }
    }
  ],
  "count": 6
}
```

**Error Codes:** 401, 403, 404 (`ORDER_NOT_FOUND`), 200 (still processing).

### 7.9 GET /api/health

System health check endpoint.

| Aspect           | Details                                              |
|------------------|------------------------------------------------------|
| **Method**       | `GET`                                                |
| **Path**         | `/health` (also `/api/health` for consistency)        |
| **Response**     | `{ "status": "ok", "cache_size": N, "redis_backend": "diskcache", ... }` |

**Production Response:**

```json
{
  "status": "ok",
  "cache_size": 1024,
  "redis_backend": "diskcache",
  "database": "connected",
  "workers": 4,
  "uptime_seconds": 86400,
  "version": "3.0.0"
}
```

**Degraded Response (503):**

```json
{
  "status": "degraded",
  "cache_size": 0,
  "redis_backend": "diskcache",
  "database": "disconnected",
  "workers": 0,
  "uptime_seconds": 86400,
  "version": "3.0.0"
}
```

### 7.10 GET /api/metrics

Prometheus-compatible metrics endpoint. Exposes order throughput, latency, failure counts, lock contention, and cache hit ratios.

| Aspect           | Details                                              |
|------------------|------------------------------------------------------|
| **Method**       | `GET`                                                |
| **Path**         | `/api/metrics`                                       |
| **Content-Type** | `text/plain; version=0.0.4`                          |
| **Response**     | Prometheus exposition format                          |

**Example Metrics Output:**

```
# HELP orchestrator_orders_total Total orders processed
# TYPE orchestrator_orders_total counter
orchestrator_orders_total{state="completed"} 1423
orchestrator_orders_total{state="failed"} 12
orchestrator_orders_total{state="cancelled"} 8

# HELP orchestrator_order_duration_seconds Order fulfillment duration
# TYPE orchestrator_order_duration_seconds histogram
orchestrator_order_duration_seconds_bucket{category="mobile",le="10"} 800
orchestrator_order_duration_seconds_bucket{category="mobile",le="30"} 1100
orchestrator_order_duration_seconds_bucket{category="mobile",le="60"} 1350
orchestrator_order_duration_seconds_bucket{category="mobile",le="+Inf"} 1400
orchestrator_order_duration_seconds_sum{category="mobile"} 28500
orchestrator_order_duration_seconds_count{category="mobile"} 1400
orchestrator_order_duration_seconds_bucket{category="l3vpn",le="10"} 400
orchestrator_order_duration_seconds_bucket{category="l3vpn",le="30"} 550
orchestrator_order_duration_seconds_bucket{category="l3vpn",le="60"} 600
orchestrator_order_duration_seconds_bucket{category="l3vpn",le="+Inf"} 610
orchestrator_order_duration_seconds_sum{category="l3vpn"} 12000
orchestrator_order_duration_seconds_count{category="l3vpn"} 600

# HELP orchestrator_cache_hits_total Pattern cache hits
# TYPE orchestrator_cache_hits_total counter
orchestrator_cache_hits_total 890

# HELP orchestrator_cache_misses_total Pattern cache misses
# TYPE orchestrator_cache_misses_total counter
orchestrator_cache_misses_total 553

# HELP orchestrator_active_locks Current active subscriber locks
# TYPE orchestrator_active_locks gauge
orchestrator_active_locks 2

# HELP orchestrator_webhook_delivery_total Webhook delivery attempts
# TYPE orchestrator_webhook_delivery_total counter
orchestrator_webhook_delivery_total{status="success"} 2840
orchestrator_webhook_delivery_total{status="failed"} 15
orchestrator_webhook_delivery_total{status="retry"} 45

# HELP orchestrator_worker_utilization Worker pool utilization
# TYPE orchestrator_worker_utilization gauge
orchestrator_worker_utilization 0.75
```

**Error Codes:** 401, 403, 500.

---

## 8. CRM Webhook Specification

> **Role:** The orchestrator pushes state changes to CRM-registered callback URLs.  
> **Delivery:** At-least-once. CRM must be idempotent on `eventId`.  
> **Signature:** HMAC-SHA256 in `X-Signature` header.

### 8.1 ServiceOrderStateChangeEvent Payload

Emitted on final state transitions (`completed`, `failed`, `cancelled`).

```
POST {callbackUrl}
Content-Type: application/json
X-TMF-Event-Type: ServiceOrderStateChangeEvent
X-Order-Id: so-l3vpn-0001
X-Correlation-Id: corr-PO-XXXXXXXX
X-Signature: sha256=b8a7f3c9d1e2456a...
```

```json
{
  "eventId": "evt-20260622-00042",
  "eventTime": "2026-06-22T09:31:05Z",
  "eventType": "ServiceOrderStateChangeEvent",
  "correlationId": "corr-ord-20260622-0001",
  "domain": "ServiceFulfillment",
  "priority": "normal",
  "timeOcurred": "2026-06-22T09:31:05Z",
  "title": "Order completed",
  "description": "Service provisioning complete. Final state: ACTIVE. All network elements configured and verified.",
  "event": {
    "serviceOrder": {
      "id": "so-l3vpn-0001",
      "href": "/api/tmf641/serviceOrder/so-l3vpn-0001",
      "externalId": "CRM-ORDER-12345",
      "state": "completed",
      "completionDate": "2026-06-22T09:31:05Z"
    }
  },
  "source": {
    "system": "TelecomOrchestrator",
    "version": "3.0.0"
  }
}
```

### 8.2 ServiceOrderMilestoneEvent Payload

Emitted for intermediate lifecycle milestones (DESIGNED → FEASIBILITY_CHECKED → ... → PCRF_CONFIGURED).

```
POST {callbackUrl}
X-TMF-Event-Type: ServiceOrderMilestoneEvent
X-Order-Id: so-l3vpn-0001
X-Signature: sha256=a1b2c3d4...
```

```json
{
  "eventId": "evt-20260622-00015",
  "eventTime": "2026-06-22T09:30:12Z",
  "eventType": "ServiceOrderMilestoneEvent",
  "correlationId": "corr-ord-20260622-0001",
  "domain": "ServiceFulfillment",
  "priority": "normal",
  "timeOcurred": "2026-06-22T09:30:12Z",
  "title": "Milestone: RESOURCE_ALLOCATED",
  "description": "Service order reached milestone: RESOURCE_ALLOCATED",
  "event": {
    "serviceOrder": {
      "id": "so-l3vpn-0001",
      "href": "/api/tmf641/serviceOrder/so-l3vpn-0001",
      "state": "inProgress",
      "externalId": "CRM-ORDER-12345",
      "category": "l3vpn",
      "milestone": [
        {
          "id": "ms-so-l3vpn-0001-RESOURCE_ALLOCATED",
          "name": "RESOURCE_ALLOCATED",
          "description": "State transition: RESOURCE_ALLOCATED",
          "message": "Resources allocated: VRF=CUST-SJC-CORP, RD=65001:1001",
          "milestoneDate": "2026-06-22T09:30:12Z",
          "status": "achieved"
        }
      ]
    }
  },
  "source": {
    "system": "TelecomOrchestrator",
    "version": "3.0.0"
  }
}
```

### 8.3 Retry Policy

| Parameter          | Value                        |
|--------------------|------------------------------|
| Max attempts       | 3 (plus initial delivery)    |
| Backoff            | Exponential: 10s, 30s, 90s   |
| Jitter             | ±20% of delay                |
| Timeout per attempt| 15 seconds                   |
| Dead-letter queue  | After 3rd failure → `webhook_dlq` Redis list |
| Ops alert          | After 3rd failure → Slack `#telco-orchestrator` / Telegram |
| Retry queue        | `webhook_delivery` queue processed by 2 RQ workers |

**Dead-letter queue entry format:**

```json
{
  "orderId": "so-l3vpn-0001",
  "eventType": "ServiceOrderStateChangeEvent",
  "callbackUrl": "https://crm.acme-corp.com/api/webhooks/telco-order-status",
  "payload": { "...full event payload..." },
  "failedAttempts": 3,
  "lastError": "Connection timeout after 15s",
  "failedAt": "2026-06-22T09:32:00Z",
  "requeuedAt": null
}
```

### 8.4 Signature Verification (HMAC-SHA256)

Every webhook includes an `X-Signature` header that CRMs can use to verify authenticity.

**Orchestrator side (signing):**

```python
import hmac, hashlib, json

def sign_webhook(payload: dict, secret: str) -> str:
    """Generate HMAC-SHA256 signature for webhook payload."""
    body = json.dumps(payload, separators=(',', ':'), sort_keys=True)
    signature = hmac.new(
        secret.encode('utf-8'),
        body.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return f"sha256={signature}"
```

**CRM side (verification, pseudocode):**

```python
import hmac, hashlib

def verify_signature(body: str, signature_header: str, secret: str) -> bool:
    expected = hmac.new(
        secret.encode('utf-8'),
        body.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    provided = signature_header.replace("sha256=", "")
    return hmac.compare_digest(expected, provided)
```

**Shared secret provisioning:**
- Secrets generated per CRM integration
- Stored in vault (Hashicorp Vault or env var `WEBHOOK_SECRET`)
- Rotated quarterly; old secrets accepted for 24h overlap window
- CRM provides public key if mTLS is configured

---

## 9. Authentication & Authorization

### 9.1 API Key Scheme

The primary authentication mechanism for service-to-service communication. API keys are passed via the `X-API-Key` header.

| Aspect              | Value                                           |
|---------------------|-------------------------------------------------|
| Header              | `X-API-Key: rm1_abcdef1234567890...`            |
| Prefix              | `rm1_` (ReadM, version 1)                       |
| Generation          | `rm1_` + 40-char hex (SHA-256 of random)        |
| Storage             | Hashed (SHA-256) in PostgreSQL `api_keys` table  |
| Rotation            | Admin endpoint: `POST /api/admin/keys/rotate`    |
| Environment override | `ORCHESTRATOR_API_KEY` env var (dev/testing)    |

**api_keys table schema:**

```sql
CREATE TABLE api_keys (
    id          SERIAL PRIMARY KEY,
    key_hash    TEXT UNIQUE NOT NULL,      -- SHA-256 of the full key
    name        TEXT NOT NULL,             -- "Salesforce Prod Integration"
    role        TEXT NOT NULL,             -- "crm", "admin", "operator", "readonly"
    scopes      TEXT[] NOT NULL,           -- {"write:order", "read:order"}
    created_by  TEXT,
    created_at  TIMESTAMPTZ DEFAULT now(),
    expires_at  TIMESTAMPTZ,
    revoked     BOOLEAN DEFAULT false,
    last_used   TIMESTAMPTZ
);
```

### 9.2 OAuth2 Client Credentials

For CRMs that prefer OAuth2 over API keys. Client credentials grant.

| Aspect              | Value                                           |
|---------------------|-------------------------------------------------|
| Grant type          | `client_credentials`                            |
| Token endpoint      | `POST /auth/token`                              |
| Token format        | JWT (RS256)                                     |
| Token lifetime      | 1 hour (access), 24 hours (refresh)             |
| Scope mapping       | CRM → `write:order read:order`                   |

**Token request:**

```
POST /auth/token
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&
client_id=salesforce-prod-001&
client_secret=********&
scope=write:order+read:order
```

**Token response:**

```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIs...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "write:order read:order"
}
```

### 9.3 Role-Based Access Control (RBAC)

| Role       | Description                              | Scopes                                    | Endpoints                                |
|------------|------------------------------------------|-------------------------------------------|------------------------------------------|
| `admin`    | Full system administration               | `*` (all)                                 | All endpoints including `/api/locks/release`, `/api/patterns/teach` |
| `operator` | Operational management and monitoring    | `write:order`, `read:order`, `read:inventory`, `read:patterns`, `read:locks`, `read:metrics` | All except `DELETE` and admin-only       |
| `readonly` | Read-only monitoring and auditing        | `read:order`, `read:inventory`, `read:patterns`, `read:metrics` | All `GET` endpoints                     |
| `crm`      | CRM system integration                   | `write:order`, `read:order`              | TMF622, TMF641 endpoints only           |

**Scope definitions:**

| Scope              | Description                                     |
|--------------------|-------------------------------------------------|
| `write:order`      | Create product/service orders (POST)            |
| `read:order`       | Read order status (GET)                         |
| `read:inventory`   | Read service/resource inventory (TMF638/TMF639) |
| `read:patterns`    | Read orchestration patterns                     |
| `write:patterns`   | Teach/inject patterns (admin)                   |
| `read:locks`       | Read lock status                                |
| `write:locks`      | Force-release locks (admin)                     |
| `read:metrics`     | Read Prometheus metrics and health              |
| `read:subscribers` | Read subscriber service models                  |

---

## 10. Error Handling

### 10.1 Standard Error Response Format

All error responses follow this structure:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Human-readable description of the error",
    "details": [
      {
        "field": "productOrderItem[0].characteristic[3].value",
        "reason": "Invalid bandwidth value: must be a positive integer"
      }
    ],
    "traceId": "abc123-def456-ghi789",
    "timestamp": "2026-06-22T09:30:00Z"
  }
}
```

| Field       | Type     | Description                                          |
|-------------|----------|------------------------------------------------------|
| `code`      | `string` | Machine-readable error code (see below)               |
| `message`   | `string` | Human-readable summary                                |
| `details`   | `array`  | Optional array of field-level validation errors       |
| `traceId`   | `string` | Correlation ID for log tracing                        |
| `timestamp` | `string` | ISO 8601 timestamp                                     |

### 10.2 HTTP Status Codes by Endpoint

| Endpoint                                      | 200/201/202 | 400  | 401  | 403  | 404  | 409  | 422  | 429  | 500  | 503  |
|-----------------------------------------------|-------------|------|------|------|------|------|------|------|------|------|
| `POST /api/tmf622/productOrder`               | 202         | ✓    | ✓    | ✓    | ✓    | ✓    | ✓    | ✓    | ✓    | ✓    |
| `GET /api/tmf622/productOrder/{id}`           | 200         | —    | ✓    | ✓    | ✓    | —    | —    | ✓    | ✓    | ✓    |
| `POST /api/tmf622/productOrder/{id}/cancel`   | 200         | ✓    | ✓    | ✓    | ✓    | ✓    | —    | ✓    | ✓    | —    |
| `POST /api/tmf641/serviceOrder`               | 201         | ✓    | ✓    | ✓    | —    | —    | ✓    | ✓    | ✓    | ✓    |
| `GET /api/tmf641/serviceOrder/{id}`           | 200         | —    | ✓    | ✓    | ✓    | —    | —    | ✓    | ✓    | —    |
| `POST /api/tmf641/serviceOrder/{id}/cancel`   | 200         | ✓    | ✓    | ✓    | ✓    | ✓    | —    | ✓    | ✓    | —    |
| `POST /api/tmf640/service`                    | 201         | ✓    | ✓    | ✓    | —    | ✓    | ✓    | ✓    | ✓    | ✓    |
| `GET /api/tmf640/service/{id}`                | 200         | —    | ✓    | ✓    | ✓    | —    | —    | ✓    | ✓    | —    |
| `PATCH /api/tmf640/service/{id}`              | 200         | ✓    | ✓    | ✓    | ✓    | ✓    | ✓    | ✓    | ✓    | —    |
| `DELETE /api/tmf640/service/{id}`             | 200         | —    | ✓    | ✓    | ✓    | ✓    | —    | ✓    | ✓    | —    |
| `GET /api/tmf638/service`                     | 200         | ✓    | ✓    | ✓    | —    | —    | —    | ✓    | ✓    | —    |
| `GET /api/tmf638/service/{id}`                | 200         | —    | ✓    | ✓    | ✓    | —    | —    | ✓    | ✓    | —    |
| `GET /api/tmf639/resource`                    | 200         | ✓    | ✓    | ✓    | —    | —    | —    | ✓    | ✓    | —    |
| `GET /api/tmf639/resource/{id}`               | 200         | —    | ✓    | ✓    | ✓    | —    | —    | ✓    | ✓    | —    |
| `GET /api/patterns`                           | 200         | —    | ✓    | ✓    | —    | —    | —    | ✓    | ✓    | —    |
| `POST /api/patterns/teach`                    | 200         | ✓    | ✓    | ✓    | —    | —    | —    | ✓    | ✓    | —    |
| `GET /api/patterns/{id}`                      | 200         | —    | ✓    | ✓    | ✓    | —    | —    | ✓    | ✓    | —    |
| `GET /api/subscribers/{id}`                   | 200         | —    | ✓    | ✓    | ✓    | —    | —    | ✓    | ✓    | —    |
| `GET /api/subscribers/{id}/diff`              | 200         | —    | ✓    | ✓    | ✓    | —    | —    | ✓    | ✓    | —    |
| `POST /api/locks/release`                     | 200         | ✓    | ✓    | ✓    | —    | —    | —    | ✓    | ✓    | —    |
| `GET /api/locks/status`                       | 200         | —    | ✓    | ✓    | —    | —    | —    | ✓    | ✓    | —    |
| `GET /api/notifications/{orderId}`            | 200         | —    | ✓    | ✓    | ✓    | —    | —    | ✓    | ✓    | —    |
| `GET /api/health`                             | 200 / 503   | —    | —    | —    | —    | —    | —    | —    | —    | —    |
| `GET /api/metrics`                            | 200         | —    | ✓    | ✓    | —    | —    | —    | ✓    | ✓    | —    |

### 10.3 Error Code Catalog

| Code                      | HTTP  | Description                                                    |
|---------------------------|-------|----------------------------------------------------------------|
| `INVALID_REQUEST`         | 400   | Malformed JSON, missing required fields, wrong Content-Type    |
| `INVALID_FILTER`          | 400   | Invalid query parameter value for inventory filtering          |
| `MISSING_PARAMETER`       | 400   | Required path/query parameter not provided                     |
| `UNAUTHORIZED`            | 401   | Missing API key, expired token, or invalid credentials         |
| `FORBIDDEN`               | 403   | Valid credentials but insufficient scope for this endpoint     |
| `NOT_FOUND`               | 404   | Resource not found (order, service, resource, subscriber)      |
| `ORDER_NOT_FOUND`         | 404   | Specific to order lookups                                      |
| `PATTERN_NOT_FOUND`       | 404   | Specific to pattern lookups                                    |
| `SERVICE_NOT_FOUND`       | 404   | Specific to service lookups                                    |
| `SUBSCRIBER_NOT_FOUND`    | 404   | Specific to subscriber lookups                                 |
| `PRODUCT_NOT_FOUND`       | 404   | Product ID not found in product catalog                        |
| `DUPLICATE_ORDER`         | 409   | `externalId` already processed (idempotency conflict)          |
| `ORDER_NOT_CANCELLABLE`   | 409   | Order already in terminal state (completed/failed/cancelled)   |
| `SERVICE_ALREADY_ACTIVE`  | 409   | Attempt to activate an already-active service                  |
| `SERVICE_NOT_MODIFIABLE`  | 409   | Service in terminal state, cannot be modified                  |
| `SERVICE_NOT_TERMINABLE`  | 409   | Service already terminated or not in active state              |
| `LOCK_CONFLICT`           | 409   | Subscriber lock held by another worker                         |
| `VALIDATION_ERROR`        | 422   | Business rule / schema validation failure                      |
| `RATE_LIMIT_EXCEEDED`     | 429   | Too many requests; `Retry-After` header provided              |
| `INTERNAL_ERROR`          | 500   | Unexpected server error                                        |
| `SERVICE_UNAVAILABLE`     | 503   | Database or Redis backend unreachable                          |

### 10.4 Validation Error Format

Detailed field-level errors conforming to TM Forum guidelines:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request body failed validation: 3 errors",
    "details": [
      {
        "field": "relatedParty",
        "reason": "At least one relatedParty with role 'customer' is required"
      },
      {
        "field": "productOrderItem[0].product.id",
        "reason": "Product 'prod-unknown-99' not found in product catalog"
      },
      {
        "field": "productOrderItem[0].characteristic[5].name",
        "reason": "Unknown characteristic: 'invalidParam'. Valid names: siteName, siteCode, bandwidth, ..."
      }
    ],
    "traceId": "trc-a1b2c3d4e5f6",
    "timestamp": "2026-06-22T09:30:00Z"
  }
}
```

---

## 11. Script Call References

Each API endpoint maps to a specific Python module and function in the production codebase.  
**Primary module:** `api/router.py` (order management), `poc/server_live.py` (orchestration engine, pattern store).  
**Config module:** `api/gateway_config.py` (Nginx config generation, rate limiting middleware).

### 11.1 TMF622 Product Ordering

| Endpoint                                      | Module / File                          | Function / Handler                    | Notes                                      |
|-----------------------------------------------|----------------------------------------|---------------------------------------|--------------------------------------------|
| `POST /api/tmf622/productOrder`               | `api/routers/tmf622.py`               | `create_product_order()`              | Validates, decomposes into ServiceOrders, enqueues |
| `GET /api/tmf622/productOrder/{id}`           | `api/routers/tmf622.py`               | `get_product_order(id)`               | Queries PostgreSQL `product_orders` table    |
| `POST /api/tmf622/productOrder/{id}/cancel`   | `api/routers/tmf622.py`               | `cancel_product_order(id)`            | Propagates cancel to all child ServiceOrders |

**Supporting modules:**
- `api/services/order_decomposition.py` — `DecompositionEngine.decompose(product_order)` → list of ServiceOrders
- `api/services/product_catalog.py` — `ProductCatalog.lookup(product_id)` → product template + decomposition rules
- `api/models/tmf622.py` — Pydantic models `ProductOrderCreate`, `ProductOrderResponse`, `ProductOrderItem`

### 11.2 TMF641 Service Ordering

| Endpoint                                      | Module / File                          | Function / Handler                    | Notes                                      |
|-----------------------------------------------|----------------------------------------|---------------------------------------|--------------------------------------------|
| `POST /api/tmf641/serviceOrder`               | `api/routers/tmf641.py`               | `create_service_order()`              | Enqueues to Redis RQ (`orders_{priority}`)  |
| `GET /api/tmf641/serviceOrder/{id}`           | `api/routers/tmf641.py`               | `get_service_order(id)`               | Returns order + audit_log + milestones     |
| `POST /api/tmf641/serviceOrder/{id}/cancel`   | `api/routers/tmf641.py`               | `cancel_service_order(id)`            | Dequeues from RQ if still pending           |

**Supporting modules:**
- `api/services/task_queue.py` — `TaskQueue.enqueue(order, priority)` → RQ job
- `api/models/tmf641.py` — Pydantic models `ServiceOrderCreate`, `ServiceOrderResponse`, `ServiceOrderItem`, `Milestone`, `AuditLogEntry`
- `api/services/audit_logger.py` — `AuditLogger.append(order_id, state, message)` → PostgreSQL + in-memory

### 11.3 TMF640 Service Activation

| Endpoint                                      | Module / File                          | Function / Handler                    | Notes                                      |
|-----------------------------------------------|----------------------------------------|---------------------------------------|--------------------------------------------|
| `POST /api/tmf640/service`                    | `api/routers/tmf640.py`                | `activate_service()`                  | Routes to orchestration pipeline            |
| `GET /api/tmf640/service/{id}`                | `api/routers/tmf640.py`                | `get_service(id)`                     | Service Inventory lookup                    |
| `PATCH /api/tmf640/service/{id}`              | `api/routers/tmf640.py`                | `modify_service(id)`                  | Triggers modify workflow                    |
| `DELETE /api/tmf640/service/{id}`             | `api/routers/tmf640.py`                | `deactivate_service(id)`              | Triggers decommission workflow              |

**Supporting modules:**
- `poc/server_live.py` — `start_pipeline(prompt)` (lines 1137–1313): core orchestration entry point
- `poc/server_live.py` — `_run_background_inner(bg_state)` (lines 1375–1709): 9-stage async pipeline
- `api/models/tmf640.py` — Pydantic models `ServiceActivationRequest`, `ServiceActivationResponse`

### 11.4 TMF638 Service Inventory

| Endpoint                                      | Module / File                          | Function / Handler                    | Notes                                      |
|-----------------------------------------------|----------------------------------------|---------------------------------------|--------------------------------------------|
| `GET /api/tmf638/service`                     | `api/routers/tmf638.py`                | `list_services(state, category, ...)`  | Queries PostgreSQL `service_inventory`      |
| `GET /api/tmf638/service/{id}`                | `api/routers/tmf638.py`                | `get_service(id)`                     | Includes related resources                  |

**Supporting modules:**
- `api/services/inventory.py` — `ServiceInventory.list_all(filters)` → paginated results
- `api/models/tmf638.py` — Pydantic models `ServiceInventoryItem`, `ServiceInventoryResponse`

### 11.5 TMF639 Resource Inventory

| Endpoint                                      | Module / File                          | Function / Handler                    | Notes                                      |
|-----------------------------------------------|----------------------------------------|---------------------------------------|--------------------------------------------|
| `GET /api/tmf639/resource`                    | `api/routers/tmf639.py`                | `list_resources(type, device, ...)`    | Queries PostgreSQL `resource_inventory`     |
| `GET /api/tmf639/resource/{id}`               | `api/routers/tmf639.py`                | `get_resource(id)`                    | Includes applied config                     |

**Supporting modules:**
- `api/services/inventory.py` — `ResourceInventory.list_all(filters)` → paginated results
- `api/models/tmf639.py` — Pydantic models `ResourceInventoryItem`, `ResourceInventoryResponse`

### 11.6 Internal Orchestrator APIs

| Endpoint                                      | Module / File                          | Function / Handler                    | Notes                                      |
|-----------------------------------------------|----------------------------------------|---------------------------------------|--------------------------------------------|
| `GET /api/patterns`                           | `poc/server_live.py` (line 1752)       | `list_patterns()`                     | `patterns.list_all()`                      |
| `POST /api/patterns/teach`                    | `poc/server_live.py` (line 1765)       | `teach_pattern(request)`              | `PatternEngine.teach(triples)`             |
| `GET /api/patterns/{id}`                      | `poc/server_live.py` (line 1757)       | `get_pattern(pattern_id)`             | `PatternEngine.get(pid)`                   |
| `GET /api/subscribers/{id}`                   | `api/routers/subscribers.py`           | `get_subscriber(id)`                  | `ServiceModelStore.get(sub_id)`            |
| `GET /api/subscribers/{id}/diff`              | `api/routers/subscribers.py`           | `get_subscriber_diff(id)`             | `ServiceModelStore.compute_diff(...)`      |
| `POST /api/locks/release`                     | `poc/server_live.py` (line 1812)       | `release_lock(request)`               | `SubscriberLock.force_release(sub_id)`     |
| `GET /api/locks/status`                       | `poc/server_live.py` (line 1821)       | `lock_status()`                       | Scans `lock:sub:*` keys in diskcache       |
| `GET /api/notifications/{orderId}`            | `poc/server_live.py` (line 1797)       | `get_notifications(order_id)`         | Reads from job.final_state.notifications   |
| `GET /api/health`                             | `poc/server_live.py` (line 1793)       | `health()`                            | `GET /health` route; also via `/api/health` |
| `GET /api/metrics`                            | `api/routers/metrics.py`               | `metrics()`                           | Prometheus client + `prometheus_fastapi_instrumentator` |

### 11.7 Core Engine Classes (poc/server_live.py)

| Class                  | Lines      | Purpose                                                   |
|------------------------|------------|-----------------------------------------------------------|
| `PatternEngine`        | 152–698    | RDF pattern store with Jaccard matching, auto-learn, teach |
| `PatternNode`          | 131–149    | Data class for a single pattern with triples and resources |
| `DataMasker`           | 981–1048   | MSISDN/IP/hostname tokenization before LLM calls           |
| `SubscriberLock`       | 1051–1133  | Per-subscriber advisory locking (30s TTL)                  |
| `ServiceModelStore`    | 34–129     | Persistent subscriber service models with corruption guard  |
| `LifecycleNotifier`    | 785–945    | TMF641 milestone and state change event emitter            |

### 11.8 Database Schema Modules

| Schema                    | Purpose                                                      |
|---------------------------|--------------------------------------------------------------|
| `api/models/db_schema.py` | SQLAlchemy ORM models for `product_orders`, `service_orders`, `service_inventory`, `resource_inventory`, `webhook_deliveries`, `api_keys` |
| `api/services/db.py`      | Database session management, connection pooling (asyncpg)    |
| `api/migrations/`         | Alembic migration scripts for schema evolution               |

### 11.9 Gateway Configuration

| File                         | Purpose                                                  |
|------------------------------|----------------------------------------------------------|
| `api/gateway_config.py`      | Generates Nginx config, TLS cert paths, CORS settings    |
| `nginx/nginx.conf`           | Deployed Nginx configuration                             |
| `nginx/conf.d/rate_limit.conf`| Rate limiting zone definitions                          |
| `certs/`                     | TLS certificate directory (mounted from host)            |

### 11.10 Deployment

| Component                    | Docker / Process                                        |
|------------------------------|---------------------------------------------------------|
| `api` (FastAPI)              | `uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4` |
| `nginx`                      | `nginx:alpine` Docker container, port 443               |
| `redis`                      | `redis:7-alpine` Docker container, port 6379            |
| `postgresql`                 | `postgres:16` Docker container, port 5432               |
| `hermes-worker-{1..4}`       | RQ workers: `rq worker orders_standard orders_urgent`   |
| `webhook-dispatcher`         | RQ worker: `rq worker webhook_delivery`                 |

---

## Appendix A: Common Headers

| Header              | Value                        | Usage                              |
|---------------------|------------------------------|------------------------------------|
| `Content-Type`      | `application/json`           | All request/response bodies        |
| `X-API-Key`         | `rm1_abcdef12345...`         | API key authentication             |
| `Authorization`     | `Bearer eyJhbGciOi...`       | OAuth2 Bearer token                |
| `X-Correlation-ID`  | `corr-ord-20260622-0001`     | Distributed tracing                |
| `X-Request-ID`      | `req-a1b2c3d4`              | Per-request tracking               |
| `X-Signature`       | `sha256=b8a7f3c9...`        | Webhook HMAC signature             |
| `X-TMF-Event-Type`  | `ServiceOrderStateChangeEvent`| Webhook event type identification |
| `X-Order-Id`        | `so-l3vpn-0001`             | Webhook order identification       |
| `Retry-After`       | `60`                         | Rate limit response (seconds)      |

## Appendix B: Typical End-to-End Flow

```
1. CRM POST /api/tmf622/productOrder  →  202 Accepted { orderId: "ord-...", serviceOrder: [...] }
2. Order Decomposition Engine creates child ServiceOrders, enqueues to Redis RQ
3. RQ Worker picks up ServiceOrder → Hermes Agent provisions network elements via MCP
4. Each milestone → webhook POST to CRM (ServiceOrderMilestoneEvent)
5. Final ACTIVE → webhook POST to CRM (ServiceOrderStateChangeEvent)
6. CRM GET /api/tmf641/serviceOrder/{id}  →  Full audit log, milestones, service ID
7. CRM GET /api/tmf638/service/{serviceId} → Service details with associated resources
8. Later: CRM POST /api/tmf640/service/{serviceId}/modify → Upgrade bandwidth
9. Later: CRM DELETE /api/tmf640/service/{serviceId} → Deactivate service
```

## Appendix C: Versioning & Compatibility

| Version | Date       | Changes                                                      |
|---------|------------|--------------------------------------------------------------|
| 3.0.0   | 2026-06-22 | Full TMF622/641/640/638/639 production APIs, Nginx gateway, webhooks |
| 2.0.0   | 2026-06-20 | PoC with POST/GET /api/process, patterns, locks, notifications |
| 1.0.0   | 2026-06-15 | Initial PoC with single `/api/process` endpoint              |

**Backward compatibility:** The `/api/process` PoC endpoint is preserved as an internal alias during migration. CRM systems should migrate to TMF622/TMF641 endpoints for production use.
