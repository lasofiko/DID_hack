ARG BASE_IMAGE=ros:jazzy-ros-base-noble
FROM node:22-bookworm-slim AS frontend
WORKDIR /app
COPY apps/frontend/package*.json ./
RUN npm ci --ignore-scripts
COPY apps/frontend/ ./
RUN npm run build

FROM ${BASE_IMAGE}
ENV DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-c"]
ARG UBUNTU_MIRROR=""
RUN printf 'Acquire::Retries "1"; Acquire::http::Timeout "30"; Acquire::https::Timeout "30";\n' > /etc/apt/apt.conf.d/80did-network && \
    if [ -n "$UBUNTU_MIRROR" ]; then sed -i "s|^URIs:.*|URIs: $UBUNTU_MIRROR|" /etc/apt/sources.list.d/ubuntu.sources; fi && \
    apt-get update && apt-get install -y --no-install-recommends \
    python3-colcon-common-extensions python3-setuptools \
    ros-jazzy-ros-gz-sim ros-jazzy-ros-gz-bridge \
    ros-jazzy-turtlebot3-gazebo ros-jazzy-robot-state-publisher \
    ros-jazzy-nav2-map-server ros-jazzy-nav2-lifecycle-manager \
    ros-jazzy-tf2-ros ros-jazzy-tf2-msgs \
    libegl1 libgl1-mesa-dri mesa-utils mesa-utils-extra xvfb xauth \
    && rm -rf /var/lib/apt/lists/*
ENV TURTLEBOT3_MODEL=burger \
    LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe LP_NUM_THREADS=4 \
    ROS_DOMAIN_ID=42 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends python3-venv && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv --system-site-packages /opt/did-web && /opt/did-web/bin/pip install --no-cache-dir fastapi==0.121.3 uvicorn==0.38.0 websockets==15.0.1 httpx==0.28.1 python-dotenv==1.2.1
ENV PATH="/opt/did-web/bin:${PATH}" DID_RUNTIME=ros DID_HOST=0.0.0.0
ENV PYTHONPATH="/workspace/DID_hack/apps/backend:/workspace/DID_hack/packages/ml:${PYTHONPATH}"
WORKDIR /workspace/DID_hack
COPY --from=frontend /app/dist apps/frontend/dist/
COPY apps/backend/ apps/backend/
COPY packages/ packages/
COPY configs/ configs/
COPY ros2/ ros2/
COPY scripts/ scripts/
COPY docker/ docker/
COPY tests/ tests/
COPY experiments/ experiments/
RUN source /opt/ros/jazzy/setup.bash && \
    /opt/did-web/bin/python /usr/bin/colcon build --base-paths ros2 --packages-select did_robot --event-handlers console_direct+
ENTRYPOINT ["/bin/bash", "/workspace/DID_hack/docker/entrypoint.sh"]
CMD ["python3", "-m", "did_backend.main"]
