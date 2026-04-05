# Requirements: CI/CD Pipeline and Kubernetes Deployment

## Overview

This document defines requirements for two additions to the Ambient Weather MCP Server:
1. A GitHub Actions CI/CD pipeline that builds and publishes Docker images
2. Kubernetes manifests for deploying the server to a cluster managed by ArgoCD

Requirements follow the EARS (Easy Approach to Requirements Syntax) format.

---

## CI/CD Pipeline Requirements

### REQ-1: Container Image Build
When a commit is pushed to the `main` branch, the system shall build a Docker
image from the repository's Dockerfile using GitHub Actions.

### REQ-2: Image Tagging
When a Docker image is built, the system shall tag it with both the Git commit
SHA (short, 7 characters) and `latest`.

### REQ-3: Image Registry
The system shall push built images to GitHub Container Registry (ghcr.io) under
the repository owner's namespace: `ghcr.io/nanagyamfiprempeh30/ambient-weather-mcp`.

### REQ-4: Registry Authentication
The pipeline shall authenticate to ghcr.io using the built-in `GITHUB_TOKEN`
secret. No additional secrets shall be required for image push.

### REQ-5: Build Caching
The pipeline should use Docker layer caching to reduce build times on
subsequent runs.

### REQ-6: Build Verification
After building the image, the pipeline shall verify the image starts
successfully by running `docker run --rm <image> python -c "from src.server import mcp; print('OK')"`.

---

## Kubernetes Deployment Requirements

### REQ-7: Deployment Resource
The system shall define a Kubernetes Deployment that runs the MCP server
container with 1 replica by default.

### REQ-8: Configuration via Environment Variables
The Deployment shall source all configuration values (AMBIENT_API_KEY,
AMBIENT_APP_KEY, CACHE_TTL_SECONDS, LOG_LEVEL) from a Kubernetes Secret
named `ambient-weather-mcp-secrets`. No configuration values shall be
hardcoded in the manifests.

### REQ-9: Health Probes
The Deployment should define a startup probe that verifies the Python
process is running. Since the MCP server uses stdio (not HTTP), traditional
HTTP health checks are not applicable.

### REQ-10: Resource Limits
The Deployment shall define resource requests (cpu: 100m, memory: 128Mi)
and limits (cpu: 500m, memory: 256Mi) for the container.

### REQ-11: Service Resource
The system shall define a ClusterIP Service that exposes the MCP server
pod on port 8080 for internal cluster communication.

### REQ-12: Ingress Resource
The system shall define an Ingress resource using Traefik as the ingress
class. The Ingress shall use the `web` entrypoint by default, consistent
with the k8s-platform-kiro design patterns.

### REQ-13: Ingress Host
The Ingress shall use a configurable hostname pattern. The default shall
be `ambient-weather-mcp.<cluster-domain>`.

### REQ-14: Observability
The system shall define a ServiceMonitor resource for Prometheus scraping.
The ServiceMonitor shall include the label `release: prometheus` to match
the kube-prometheus-stack selector, consistent with the k8s-platform-kiro
design patterns.

### REQ-15: Namespace
All Kubernetes resources shall be deployed to a dedicated namespace named
`ambient-weather-mcp`.

### REQ-16: ArgoCD Compatibility
The manifests shall be structured as plain YAML files in a `kubernetes/`
directory at the repository root, suitable for ArgoCD directory-type
application sync.

### REQ-17: Secret Template
The system shall include a `secret.yaml.example` template showing the
required secret keys with placeholder values. The actual `secret.yaml`
shall be excluded from version control via `.gitignore`.

---

## Transport Consideration

Note: The MCP server currently operates in stdio mode (stdin/stdout JSON-RPC),
which is designed for local process execution, not network serving. For
Kubernetes deployment, the server would need to be extended to support HTTP
Streamable transport (SSE or streamable-http mode). This is documented as a
future requirement but the manifests should be structured to accommodate this
transition. REQ-11 and REQ-12 anticipate this by defining Service and Ingress
resources that will become active once HTTP transport is implemented.
