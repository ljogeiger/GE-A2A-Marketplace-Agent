# Gemini Enterprise A2A Marketplace Agent

This repository provides a comprehensive, step-by-step roadmap for building, securing, deploying, and listing an **Agent-as-a-Service (AaaS)** solution on the Google Cloud Marketplace. It is designed to help partners navigate the technical requirements of the **Agent2Agent (A2A)** protocol and seamless integration with **Gemini Enterprise**.

## Overview

A key requirement for listing AI agents on Cloud Marketplace is adherence to the Agent2Agent (A2A) protocol. This standard enables smooth integration between different AI agents and agentic AI platforms like Gemini Enterprise. Instead of building traditional Software-as-a-Service (SaaS) solutions with custom APIs, this project demonstrates how to offer **Agent-as-a-Service**.

We start with a simple local agent and progressively evolve it into a production-ready, Marketplace-integrated solution.

## Description Video

At the end of Step 5 you will be able to 
1. Procure an agent from GCP Agent Marketplace through a Private Offer. Video [here](https://www.youtube.com/watch?v=AJI_C_xVo_E)
2. Register that agent into Gemini Enterprise through Dynamic Client Registration
3. Use the Agent with end-user credentials using Oauth2.0 Application Code Flow 

Video for steps 2 and 3 is [here](https://www.youtube.com/watch?v=7TLacPDYDHM)

[![Watch the video](https://img.youtube.com/vi/7TLacPDYDHM/maxresdefault.jpg)](https://youtu.be/7TLacPDYDHM)

## Step-by-Step Guide

The project is divided into 6 distinct steps, each building upon the last.

| Step | Directory | Goal | Key Concepts |
| :--- | :--- | :--- | :--- |
| **0** | [`0_adk_agent`](./0_adk_agent/) | **Basic Agent Setup** | Getting started with the Google Agent Development Kit (ADK) to run a simple local agent. |
| **1** | [`1_a2a`](./1_a2a/) | **A2A Communication** | Decoupling the system into a **Client Agent** and a **Remote Service Agent**. Demonstrates the core A2A pattern where one agent delegates tasks to another. |
| **2** | [`2_oauth`](./2_oauth/) | **Security (OAuth 2.0)** | Wrapping the remote agent in a custom **FastAPI** server to enforce **OAuth 2.0** authentication (via Okta). Implementation of custom scopes (`agent:time`) and middleware. |
| **3** | [`3_deploy_agent`](./3_deploy_agent/) | **Cloud Deployment** | Deploying the secure agent to **Google Cloud Run**. Handling the "circular dependency" of Agent Card URLs and managing secrets via **Google Secret Manager**. |
| **4** | [`4_add_DCR`](./4_add_DCR/) | **Dynamic Client Registration** | Implementing the **DCR** protocol. This allows Gemini Enterprise to programmatically register itself as an OAuth client with your agent, eliminating manual key exchange. |
| **5** | [`5_gcp_marketplace_setup`](./5_gcp_marketplace_setup/) | **Marketplace Integration** | The complete production integration. Connects **Marketplace Procurement** (Pub/Sub) with **Agent Registration** (DCR) using **Firestore** to validate orders and manage entitlements. |

## Overall Security

Security is a foundational element of this architecture, designed to meet enterprise standards.

*   **OAuth 2.0 Authorization Code Flow**: We use the standard flow for delegated user authorization, ensuring users explicitly grant access to the agent.
*   **Least Privilege (Scopes)**: We implement custom scopes (e.g., `agent:time`) so that access tokens only grant permission for specific actions, preventing over-privileged access.
*   **Dynamic Client Registration (DCR)**: Automates the secure exchange of credentials. We validate **Google-signed JWTs** to ensure that registration requests originate from legitimate Gemini Enterprise instances.
*   **Infrastructure Security**:
    *   **Secret Manager**: All sensitive keys (Okta tokens, client secrets) are stored in Google Secret Manager, never in code or environment variables.
    *   **Service Accounts**: We use distinct Service Accounts for the Runtime (Cloud Run) and Invocation (Pub/Sub) to strictly limit permissions.
    *   **Firestore Validation**: In Step 5, we cross-reference incoming DCR requests with verified Marketplace Orders stored in Firestore to prevent spoofing.

---

## Feature / Roadmap

The following table outlines the current feature support and future roadmap for the project.

| Feature                       | Support | Notes                                                              |
| :---------------------------- | :------ | :----------------------------------------------------------------- |
| Dynamic Client Registration (DCR) | :white_check_mark:     | Fully implemented for Okta.                                        |
| IDP: Okta                     | :white_check_mark:     | Current Identity Provider. Other IDPs could be integrated.         |
| OAuth ADK Agent               | :white_check_mark:     | Agent integrates with OAuth for secure A2A communication.          |
| A2A (Agent-to-Agent)          | :white_check_mark:     | Core functionality, remote agent communication.                    |
| Marketplace Procurement       | :white_check_mark:     | Integration with GCP Marketplace Procurement APIs and Pub/Sub.     |
| Order Database: Firestore     | :white_check_mark:     | Used for persisting order and client mappings.                     |
| Private Offers                | :white_check_mark:     | Supported with DCR and manual credential exchange.                 |
| Agent Runtime: Cloud Run      | :white_check_mark:      | A2A Agent runs on Cloud Run         |
| Usage-based pricing metering  | :x:      | Future work: Implement usage tracking and reporting to GCP.        |
| Subscription throttling       | :x:      | Future work: Implement rate-limiting based on subscription tiers.  |
| Deprovisioning of resources   | :x:      | Future work: Handle Pub/Sub notifications for order cancellation.  |
| A2UI (Agent-to-UI)            | :x:      | Future work: Integration with rich UIs for agent interaction.      |
| Public Offers                 | :x:      | Current implementation focuses on Private Offers due to DCR scope. |
| Streaming (A2A Protocol)      | :x:      | Future work: Implement A2A streaming interaction patterns.         |
| Agent Runtime: Agent Engine      | :x:      | Future work: Implement Agent Engine as the runtime for the agent         |

---

# Integrating Your AI Agent with Google Cloud Marketplace: Partner Guide

## Objectives
This document outlines guidelines for Marketplace partners on how to build and list AI agents on Google Cloud Marketplace as **Agent-as-a-Service (AaaS)** solutions. AaaS offerings provide ready-to-use AI agents that interoperate with other agents and platforms via the standardized **Agent2Agent (A2A)** protocol.

## Requirements
All products offered through Cloud Marketplace must comply with standard Marketplace listing requirements. AI agents must also meet the following additional requirements:

1.  **A2A Protocol Adherence**: Comply with the A2A protocol specification.
2.  **A2A Agent Card**: Provide a valid A2A Agent Card to declare the agent's capabilities (skills), authentication, and endpoints.
3.  **Authentication/Authorization**: Implement a supported authentication/authorization method (OAuth 2.0).
4.  **Gemini Enterprise Integration**: Enable seamless integration with Gemini Enterprise, preferably implementing **Dynamic Client Registration (DCR)** for automatic registration.
5.  **Marketplace Procurement Integration**: Integrate with Marketplace Procurement APIs and Pub/Sub for entitlement lifecycle management.
6.  (Optional)**Usage Metering**: Meter usage and/or resource utilization if offering usage-based pricing.
7.  (Optional)**Usage Reporting**: Report metered usage to Google's Service Control API.
8.  (Optional)**Throttling**: Implement mechanisms to restrict resource utilization.

## A2A Agent Card
To list your product, you must provide an **Agent Card** (`agent.json`). Gemini Enterprise relies on this card to:
*   Display Agent name and description.
*   Locate endpoints for DCR.
*   Discover agent entry points.
*   Determine required authentication methods.

## Authentication/Authorization
To allow Gemini Enterprise to call your agent, you must support **OAuth 2.0 Authorization Code Grant Flow**.
*   **Public Access**: Only for agents touching no user/sensitive data.
*   **OAuth 2.0**: The standard flow. Users will be prompted to authorize your agent.

## Dynamic Client Registration (DCR)
DCR allows Gemini Enterprise to programmatically register as an OAuth 2.0 client.

### DCR Endpoint Implementation
Your DCR endpoint will receive a POST request with a **Software Statement** (JWT).

**Request Body:**
```json
{
   "software_statement": "<software_statement_jwt>"
}
```

**JWT Payload Validation:**
You must verify the JWT signature (using Google's public keys), expiration, audience, and the `google.order` claim against your procurement records.

**Response:**
Upon success, return a new Client ID and Secret:
```json
{
   "client_id": "<newly_created_client_id>",
   "client_secret": "<newly_created_client_secret>",
   "client_secret_expires_at": 0
}
```

## End-to-End Data Flow

1.  **Partner Enrollment**: Become a Google Cloud Build Partner.
2.  **Agent Development**: Implement A2A protocol, Agent Card, and DCR endpoint.
3.  **Marketplace Listing**: Create "AI Agent as a Service" product, upload Agent Card, integrate Procurement.
4.  **Customer Procurement**: Customer purchases agent.
5.  **Entitlement Activation**: Agent backend receives Pub/Sub notification (Flow 1 in Step 5).
6.  **Agent Registration**: Customer adds agent to Gemini Enterprise. DCR endpoint is called (Flow 2 in Step 5).
7.  **Agent Usage**: Gemini Enterprise generates access tokens and calls your agent's `SendMessage` endpoint.
8.  **Billing**: Agent reports usage (if applicable) to Google Service Control API.

## Comparison: SaaS vs. AaaS

| Feature | Standard SaaS | AI Agent as Service (AaaS) |
| :--- | :--- | :--- |
| **API** | Any custom API | Must adhere to A2A |
| **Auth** | Any method | OAuth 2.0 Authorization Code Flow |
| **Frontend** | Custom App | Not supported (managed by Gemini Ent.) |
| **Registration** | Manual Sign-up | Automatic via DCR |
| **Integration** | Manual | Seamless |

## References
*   [A2A Protocol](https://a2a-protocol.org/latest/)
*   [A2A Agent Card Specification](https://a2a-protocol.org/dev/specification/)
*   [RFC 7591 (DCR Protocol)](https://datatracker.ietf.org/doc/html/rfc7591)
*   [Google Public Keys for JWT](https://www.googleapis.com/service_accounts/v1/metadata/x509/cloud-agentspace@system.gserviceaccount.com)
