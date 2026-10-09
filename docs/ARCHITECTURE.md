# ScanForge Architecture (docs/ARCHITECTURE.md)

Detailed system architecture, components, and data flow for ScanForge.

---

## 1. System Topology

```mermaid
flowchart TD
    subgraph Client ["Client Browser"]
        UI["React 18 + Vite + Tailwind UI"]
        Viewer["3D Viewer (Three.js & Splat Viewer)"]
    end

    subgraph ReverseProxy ["Nginx Ingress (:80 -> :3000)"]
        NGX["Nginx Proxy (Buffering OFF)"]
    end

    subgraph AppServer ["FastAPI Application Server (:8000)"]
        Router["FastAPI Routers (/api)"]
        Auth["CORS & Origin Validation"]
        Upload["Streaming Upload Handler"]
        DBEngine["SQLModel Engine (SQLite / Postgres)"]
    end

    subgraph JobQueue ["Asynchronous Processing"]
        Redis[("Redis 7.4 (Broker & Pub/Sub)")]
        MockWorker["RQ Worker (scanforge_mock)"]
        GPUWorker["RQ Worker (scanforge_gpu)"]
    end

    subgraph Storage ["Persistent Volume (/data)"]
        Uploads["uploads/{job_id}/"]
        Workdirs["jobs/{job_id}/"]
        Artifacts["artifacts/{job_id}/"]
        DBFile["scanforge.db"]
    end

    UI -->|"HTTP REST & Uploads"| NGX
    UI -->|"SSE Progress"| NGX
    NGX --> Router
    Router --> Upload
    Upload --> Uploads
    Router --> Redis
    Redis --> MockWorker
    Redis --> GPUWorker
    MockWorker --> Storage
    GPUWorker --> Storage
    Router --> DBEngine
    DBEngine --> DBFile
    MockWorker -->|"Pub/Sub Progress"| Redis
    GPUWorker -->|"Pub/Sub Progress"| Redis
    Redis -->|"SSE Stream"| Router
```

---

## 2. Docker Compose Profiles

To avoid compiling heavy CUDA and C++ libraries during local frontend or API development, ScanForge isolates environments using Compose profiles:

| Profile | Active Services | Purpose |
|---|---|---|
| `mock` (Default) | `frontend`, `api`, `worker-mock`, `redis` | Rapid development with procedural 3D mock engine. |
| `gpu` | `frontend`, `api`, `worker-gpu`, `redis` | Production reconstruction with CUDA, COLMAP, OpenMVS, and Nerfstudio. |
| `test` | `test-frontend` | Frontend unit and Playwright integration tests. |

Separate RQ queues (`scanforge_mock` vs `scanforge_gpu`) ensure that tasks are dispatched strictly to workers matching the intended execution mode.

---

## 3. Pipeline Framework Abstraction

Reconstruction tasks are broken into discrete, testable `Stage` units:

```python
class Stage(ABC):
    name: str
    weight: float
    timeout_seconds: int = 7200

    @abstractmethod
    def run(self, ctx: JobContext) -> StageResult:
        ...

    def get_params_hash(self, ctx: JobContext) -> str:
        ...
```

### Stage Idempotence and Crash Recovery
- Prior to executing each stage, the framework computes a SHA-256 hash of its parameters and input artifact states.
- If expected outputs exist in `ctx.workdir` and match the hash recorded in metadata, the stage is skipped.
- When `/calibrate` is invoked, only `ScaleStage` and downstream stages are marked dirty; upstream stages (SfM, point cloud densification, mesh reconstruction) are retrieved from cache.
