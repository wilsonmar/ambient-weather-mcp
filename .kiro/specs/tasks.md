# Tasks: CI/CD Pipeline and Kubernetes Deployment

## Overview

Sequenced implementation tasks derived from design.md. Each task produces
one or more files and can be verified independently.

---

## Task 1: GitHub Actions Workflow

**Implements:** REQ-1, REQ-2, REQ-3, REQ-4, REQ-5, REQ-6

**Create:** `.github/workflows/build-and-push.yml`

**Acceptance criteria:**
- Workflow triggers on push to `main` branch
- Builds Docker image using Buildx with GHA cache
- Authenticates to ghcr.io with GITHUB_TOKEN
- Tags image with commit SHA (7-char) and `latest`
- Runs smoke test: `python -c "from src.server import mcp; print('OK')"`
- Pushes both tags to ghcr.io/nanagyamfiprempeh30/ambient-weather-mcp
- Pull requests build but do NOT push

**Verify:** Push a commit to main, check Actions tab for green build,
verify image appears at ghcr.io.

---

## Task 2: Kubernetes Namespace

**Implements:** REQ-15

**Create:** `kubernetes/namespace.yaml`

**Acceptance criteria:**
- Defines namespace `ambient-weather-mcp`
- Valid YAML, passes `kubectl apply --dry-run=client`

---

## Task 3: Kubernetes Secret Template

**Implements:** REQ-8, REQ-17

**Create:** `kubernetes/secret.yaml.example`
**Update:** `.gitignore` to exclude `kubernetes/secret.yaml`

**Acceptance criteria:**
- Contains all four env vars: AMBIENT_API_KEY, AMBIENT_APP_KEY,
  CACHE_TTL_SECONDS, LOG_LEVEL
- Uses placeholder values, not real keys
- Comments explain how to create the actual secret
- `kubernetes/secret.yaml` is in `.gitignore`

---

## Task 4: Kubernetes Deployment

**Implements:** REQ-7, REQ-8, REQ-9, REQ-10

**Create:** `kubernetes/deployment.yaml`

**Acceptance criteria:**
- 1 replica
- Image: ghcr.io/nanagyamfiprempeh30/ambient-weather-mcp:latest
- Environment from secret `ambient-weather-mcp-secrets` via envFrom
- Resource requests: cpu=100m, memory=128Mi
- Resource limits: cpu=500m, memory=256Mi
- Startup probe: exec command `python -c "from src.server import mcp; print('OK')"`
- Security context: runAsNonRoot=true, readOnlyRootFilesystem=true
- No hardcoded configuration values

---

## Task 5: Kubernetes Service

**Implements:** REQ-11

**Create:** `kubernetes/service.yaml`

**Acceptance criteria:**
- ClusterIP type
- Port 8080 targeting container port 8080
- Selector matches deployment pod labels
- Namespace: ambient-weather-mcp

---

## Task 6: Kubernetes Ingress

**Implements:** REQ-12, REQ-13

**Create:** `kubernetes/ingress.yaml`

**Acceptance criteria:**
- IngressClassName: traefik
- Annotation: `traefik.ingress.kubernetes.io/router.entrypoints: web`
- Host: `ambient-weather-mcp.local` (configurable)
- Backend: service on port 8080
- Namespace: ambient-weather-mcp

---

## Task 7: Kubernetes ServiceMonitor

**Implements:** REQ-14

**Create:** `kubernetes/servicemonitor.yaml`

**Acceptance criteria:**
- Label: `release: prometheus`
- Targets port 8080, path `/metrics`
- Namespace: ambient-weather-mcp
- Selector matches service labels

---

## Task 8: Update .gitignore

**Implements:** REQ-17

**Update:** `.gitignore`

**Acceptance criteria:**
- `kubernetes/secret.yaml` is excluded
- Existing gitignore entries preserved

---

## Execution Order

Tasks must be executed in order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8

Task 1 (CI/CD) is independent and can be verified immediately via
GitHub Actions. Tasks 2-7 (Kubernetes) form a dependency chain and
should be applied together to a cluster for verification.
