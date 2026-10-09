# ScanForge GPU Worker Dockerfile (Multi-stage build for RTX 4060 / Ada Lovelace compute 8.9)
# Used with docker compose --profile gpu up

# Stage 1: Build COLMAP with CUDA
FROM nvidia/cuda:12.1.1-devel-ubuntu22.04 AS colmap-builder
ENV DEBIAN_FRONTEND=noninteractive
ENV CUDA_ARCHITECTURES=89

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    ninja-build \
    libboost-program-options-dev \
    libboost-filesystem-dev \
    libboost-graph-dev \
    libboost-system-dev \
    libeigen3-dev \
    libfreeimage-dev \
    libmetis-dev \
    libgoogle-glog-dev \
    libgflags-dev \
    libsqlite3-dev \
    libceres-dev \
    && rm -rf /var/lib/apt/lists/*

# Pinned COLMAP 3.9.1 build
WORKDIR /src
RUN git clone --depth 1 --branch 3.9.1 https://github.com/colmap/colmap.git /src/colmap && \
    mkdir /src/colmap/build && cd /src/colmap/build && \
    cmake .. -GNinja \
      -DCMAKE_BUILD_TYPE=Release \
      -DCUDA_ENABLED=ON \
      -DCMAKE_CUDA_ARCHITECTURES=89 \
      -DCMAKE_INSTALL_PREFIX=/opt/colmap && \
    ninja install

# Stage 2: Build OpenMVS
FROM nvidia/cuda:12.1.1-devel-ubuntu22.04 AS openmvs-builder
ENV DEBIAN_FRONTEND=noninteractive
ENV CUDA_ARCHITECTURES=89

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    libboost-all-dev \
    libeigen3-dev \
    libopencv-dev \
    libcgal-dev \
    libceres-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN git clone --depth 1 --branch v2.2.0 https://github.com/cdcseacave/openMVS.git /src/openmvs && \
    mkdir /src/openmvs/build && cd /src/openmvs/build && \
    cmake .. \
      -DCMAKE_BUILD_TYPE=Release \
      -DOpenMVS_USE_CUDA=ON \
      -DCUDA_ARCH_NAME="Manual" \
      -DCUDA_ARCH_BIN="89" \
      -DCMAKE_INSTALL_PREFIX=/opt/openmvs && \
    make -j$(nproc) && make install

# Stage 3: Python Runtime with PyTorch, Nerfstudio, Open3D, Trimesh, and Blender
FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04 AS runtime
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PATH="/opt/colmap/bin:/opt/openmvs/bin:${PATH}"

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-dev \
    python3.11-venv \
    python3-pip \
    ffmpeg \
    blender \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy built binaries from stages
COPY --from=colmap-builder /opt/colmap /opt/colmap
COPY --from=openmvs-builder /opt/openmvs /opt/openmvs

WORKDIR /workspace

# Install Python requirements
COPY backend/pyproject.toml /workspace/backend/
RUN pip3 install --no-cache-dir --upgrade pip setuptools wheel && \
    pip3 install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cu121 && \
    pip3 install --no-cache-dir ./backend[gpu]

COPY backend /workspace/backend
WORKDIR /workspace/backend

CMD ["python3", "-m", "app.queue.worker", "--queue", "scanforge_gpu"]
