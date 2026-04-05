# Design: CI/CD Pipeline and Kubernetes Deployment

## Overview

This document describes the technical design for implementing the CI/CD
pipeline (REQ-1 through REQ-6) and Kubernetes manifests (REQ-7 through
REQ-17) for the Ambient Weather MCP Server.

---

## 1. CI/CD Pipeline Design

### 1.1 Workflow File

**File:** `.github/workflows/build-and-push.yml`

**Trigger:** Push to `main` branch only. Pull requests run build but do
not push to registry. (REQ-1)

**Steps:**

1. Checkout code
2. Set up Docker Buildx (enables build caching)
3. Authenticate to ghcr.io using `GITHUB_TOKEN` (REQ-4)
4. Extract metadata: commit SHA (short 7-char) for tagging (REQ-2)
5. Build Docker image with layer caching via GitHub Actions cache (REQ-5)
6. Verify image by running a smoke test command (REQ-6)
7. Push image to `ghcr.io/nanagyamfiprempeh30/ambient-weather-mcp` with
   both `:latest` and `:<sha>` tags (REQ-2, REQ-3)

**Design decisions:**

- Use `docker/build-push-action@v5` for Buildx integration and cache support
- Use `docker/metadata-action@v5` for automated tag generation
- Use `docker/login-action@v3` for registry authentication
- Build caching uses GitHub Actions cache backend (`type=gha`) rather than
  registry-based caching to avoid permission complexity
- Smoke test runs the built image with a Python import check, not a full
  API call (no API keys needed in CI)

### 1.2 Image Naming Convention

```
ghcr.io/nanagyamfiprempeh30/ambient-weather-mcp:latest
ghcr.io/nanagyamfiprempeh30/ambient-weather-mcp:a1b2c3d
```

The short SHA tag allows pinning deployments to specific commits while
`latest` enables simple local testing.

---

## 2. Kubernetes Manifests Design

### 2.1 Directory Structure

```
kubernetes/
├── namespace.yaml
├── secret.yaml.example      # Template with placeholder values (committed)
├── deployment.yaml
├── service.yaml
├── ingress.yaml
└── servicemonitor.yaml
```

Actual `secret.yaml` is added to `.gitignore`. (REQ-17)

ArgoCD will be configured to sync from the `kubernetes/` directory. (REQ-16)

### 2.2 Namespace (REQ-15)

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: ambient-weather-mcp
```

### 2.3 Secret (REQ-8, REQ-17)

The secret stores API keys and optional configuration:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: ambient-weather-mcp-secrets
  namespace: ambient-weather-mcp
type: Opaque
stringData:
  AMBIENT_API_KEY: "<your-api-key>"
  AMBIENT_APP_KEY: "<your-application-key>"
  CACHE_TTL_SECONDS: "60"
  LOG_LEVEL: "INFO"
```

The `secret.yaml.example` commits with placeholder values. The actual
`secret.yaml` is created manually on the cluster or injected via an
external secrets operator.

### 2.4 Deployment (REQ-7, REQ-8, REQ-9, REQ-10)

**Image:** `ghcr.io/nanagyamfiprempeh30/ambient-weather-mcp:latest`

**Replicas:** 1 (MCP stdio mode is single-process; scaling requires HTTP
transport, which is a future requirement)

**Environment variables:** All sourced from the Secret via `envFrom`. (REQ-8)

**Probes:** A command-based startup probe runs
`python -c "from src.server import mcp; print('OK')"` to verify the
application loads without import errors. Liveness and readiness probes
are omitted because stdio mode does not expose an HTTP endpoint. These
will be added when HTTP transport is implemented. (REQ-9)

**Resources:** (REQ-10)
- Requests: cpu=100m, memory=128Mi
- Limits: cpu=500m, memory=256Mi

**Security context:** `runAsNonRoot: true`, `readOnlyRootFilesystem: true`
matching the Dockerfile's non-root user.

### 2.5 Service (REQ-11)

ClusterIP service on port 8080 targeting the deployment pods. This
service is defined for forward-compatibility with HTTP transport. In
stdio mode, the service exists but receives no traffic.

### 2.6 Ingress (REQ-12, REQ-13)

Traefik IngressRoute-style Ingress using the standard `networking.k8s.io/v1`
API with Traefik-specific annotations:

```yaml
annotations:
  traefik.ingress.kubernetes.io/router.entrypoints: web
```

**Ingress class:** `traefik` (REQ-12)

**Host:** Configurable, default `ambient-weather-mcp.local` (REQ-13).
In a real cluster this would be `ambient-weather-mcp.<cluster-ip>.nip.io`.

### 2.7 ServiceMonitor (REQ-14)

Defines a Prometheus ServiceMonitor with:

```yaml
metadata:
  labels:
    release: prometheus
```

This label is required for the kube-prometheus-stack's Prometheus Operator
to discover and scrape the target. The monitor targets port 8080 and
path `/metrics`. Actual metrics export requires a future code change to
add a `/metrics` endpoint (using `prometheus_client` Python library).

---

## 3. Transport Gap Analysis

The current MCP server runs in stdio mode only. The Kubernetes manifests
are designed for HTTP transport which requires:

1. Adding `--mode streamable-http` support to `server.py` (FastMCP supports
   this natively via `mcp.run(transport="streamable-http")`)
2. Exposing a port (8080) for the HTTP server
3. Adding a `/health` endpoint for proper Kubernetes probes
4. Adding a `/metrics` endpoint for Prometheus scraping

These changes are deferred to a future phase. The manifests are written
now so that the Kubernetes deployment is ready when HTTP transport is added.

---

## 4. ArgoCD Application Configuration

ArgoCD application YAML (applied manually, not in the `kubernetes/` directory):

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: ambient-weather-mcp
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/NanaGyamfiPrempeh30/ambient-weather-mcp
    targetRevision: main
    path: kubernetes
  destination:
    server: https://kubernetes.default.svc
    namespace: ambient-weather-mcp
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```
