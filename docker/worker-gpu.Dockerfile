# ScanForge GPU Worker Dockerfile (RTX 4060 / Ada Lovelace compute capability 8.9)
# Profiles: gpu

# ==============================================================================
# Stage 1: Build COLMAP 3.9.1 with CUDA
# ==============================================================================
FROM nvidia/cuda:12.1.1-devel-ubuntu22.04 AS colmap-builder
ENV DEBIAN_FRONTEND=noninteractive
ENV CUDA_ARCHITECTURES=89

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
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
    libglew-dev \
    libgl1-mesa-dev \
    libflann-dev \
    liblz4-dev \
    libcgal-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN git clone --recurse-submodules --depth 1 --branch 3.9.1 https://github.com/colmap/colmap.git /src/colmap && \
    mkdir -p /src/colmap/build && cd /src/colmap/build && \
    cmake .. -GNinja \
      -DCMAKE_BUILD_TYPE=Release \
      -DCUDA_ENABLED=ON \
      -DCMAKE_CUDA_ARCHITECTURES=89 \
      -DGUI_ENABLED=OFF \
      -DTESTS_ENABLED=OFF \
      -DCMAKE_INSTALL_PREFIX=/opt/colmap && \
    ninja -j3 install

# ==============================================================================
# Stage 2: Build OpenMVS v2.2.0 with CUDA
# ==============================================================================
FROM nvidia/cuda:12.1.1-devel-ubuntu22.04 AS openmvs-builder
ENV DEBIAN_FRONTEND=noninteractive
ENV LD_LIBRARY_PATH="/usr/local/cuda/lib64/stubs:${LD_LIBRARY_PATH}"

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    libpng-dev \
    libjpeg-dev \
    libtiff-dev \
    libglu1-mesa-dev \
    libglew-dev \
    libglfw3-dev \
    libboost-all-dev \
    libopencv-dev \
    libcgal-dev \
    libcgal-qt5-dev \
    libceres-dev \
    libeigen3-dev \
    && rm -rf /var/lib/apt/lists/*

# Create stub symlink so linker finds libcuda during image build
RUN ln -sf /usr/local/cuda/lib64/stubs/libcuda.so /usr/local/cuda/lib64/stubs/libcuda.so.1

WORKDIR /src
RUN git clone --depth 1 https://github.com/cdcseacave/VCG.git /src/vcglib && \
    git clone --depth 1 --branch v2.2.0 https://github.com/cdcseacave/openMVS.git /src/openmvs && \
    mkdir -p /src/openmvs/build && cd /src/openmvs/build && \
    cmake .. \
      -DCMAKE_BUILD_TYPE=Release \
      -DVCG_ROOT=/src/vcglib \
      -DOpenMVS_USE_CUDA=ON \
      -DCMAKE_LIBRARY_PATH=/usr/local/cuda/lib64/stubs/ \
      -DCUDA_TOOLKIT_ROOT_DIR=/usr/local/cuda/ \
      -DCUDA_INCLUDE_DIRS=/usr/local/cuda/include/ \
      -DCUDA_CUDART_LIBRARY=/usr/local/cuda/lib64 \
      -DCUDA_NVCC_EXECUTABLE=/usr/local/cuda/bin/nvcc \
      -DCUDA_ARCH_NAME="Manual" \
      -DCUDA_ARCH_BIN="8.9" \
      -DCMAKE_INSTALL_PREFIX=/opt/openmvs && \
    make -j3 && make install && \
    if [ -d /opt/openmvs/bin/OpenMVS ]; then cp -rs /opt/openmvs/bin/OpenMVS/* /opt/openmvs/bin/; fi

# ==============================================================================
# Stage 3: Python Runtime with PyTorch, Open3D, Trimesh, FFmpeg, and Blender
# ==============================================================================
FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04 AS runtime
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PATH="/opt/venv/bin:/opt/colmap/bin:/opt/openmvs/bin:/opt/openmvs/bin/OpenMVS:${PATH}"
ENV LD_LIBRARY_PATH="/opt/openmvs/lib:/opt/colmap/lib:${LD_LIBRARY_PATH}"
ENV PYTHONPATH="/workspace/backend:${PYTHONPATH}"

# Install system dependencies, libraries for OpenMVS/COLMAP, and deadsnakes Python 3.11
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    ca-certificates \
    curl \
    xz-utils \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    libboost-program-options-dev \
    libboost-filesystem-dev \
    libboost-graph-dev \
    libboost-system-dev \
    libboost-iostreams-dev \
    libboost-serialization-dev \
    libfreeimage-dev \
    libgoogle-glog-dev \
    libgflags-dev \
    libsqlite3-dev \
    libceres-dev \
    libopencv-dev \
    libcgal-dev \
    libglew-dev \
    libglu1-mesa-dev \
    libflann-dev \
    liblz4-dev \
    libsm6 \
    libice6 \
    libegl1 \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-dev \
    python3.11-venv \
    && rm -rf /var/lib/apt/lists/*

# Install pinned Blender 4.1.0 for headless DCC conversions (FBX/USDZ)
RUN curl -sSL https://download.blender.org/release/Blender4.1/blender-4.1.0-linux-x64.tar.xz | tar -xJ -C /opt/ && \
    ln -sf /opt/blender-4.1.0-linux-x64/blender /usr/local/bin/blender

# Copy compiled binaries from builder stages and symlink to /usr/local/bin
COPY --from=colmap-builder /opt/colmap /opt/colmap
COPY --from=openmvs-builder /opt/openmvs /opt/openmvs
RUN ln -sf /opt/colmap/bin/colmap /usr/local/bin/colmap && \
    if [ -d /opt/openmvs/bin/OpenMVS ]; then \
      for f in /opt/openmvs/bin/OpenMVS/*; do \
        [ -f "$f" ] && ln -sf "$f" /usr/local/bin/$(basename "$f"); \
      done; \
    fi && \
    if [ -d /opt/openmvs/bin ]; then \
      for f in /opt/openmvs/bin/*; do \
        [ -f "$f" ] && ln -sf "$f" /usr/local/bin/$(basename "$f"); \
      done; \
    fi

# Setup Python 3.11 virtual environment
RUN python3.11 -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --upgrade pip setuptools wheel && \
    ln -sf /opt/venv/bin/python /usr/local/bin/python && \
    ln -sf /opt/venv/bin/python /usr/local/bin/python3 && \
    ln -sf /opt/venv/bin/pip /usr/local/bin/pip && \
    ln -sf /opt/venv/bin/pip /usr/local/bin/pip3

# Install PyTorch with CUDA 12.1 and headless OpenCV
RUN --mount=type=cache,target=/root/.cache/pip \
    /opt/venv/bin/pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121 && \
    /opt/venv/bin/pip install opencv-python-headless

# Install backend dependencies (Open3D, Trimesh, FastAPI, etc. - no nerfstudio yet)
WORKDIR /workspace
COPY backend /workspace/backend
COPY scripts /workspace/scripts
RUN ln -s /workspace/scripts /workspace/backend/scripts
RUN --mount=type=cache,target=/root/.cache/pip \
    /opt/venv/bin/pip install -e /workspace/backend[dev]

WORKDIR /workspace/backend
CMD ["python3", "-m", "app.queue.worker", "--queue", "scanforge_gpu"]
