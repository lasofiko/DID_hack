#!/usr/bin/env bash
set -e
source /opt/ros/jazzy/setup.bash
source /workspace/DID_hack/install/setup.bash
export GZ_SIM_RESOURCE_PATH="$(ros2 pkg prefix turtlebot3_gazebo)/share/turtlebot3_gazebo/models:${GZ_SIM_RESOURCE_PATH:-}"
if [ "${RENDER_MODE:-egl}" = xvfb ]; then
    export DISPLAY=:99
    Xvfb :99 -screen 0 1280x720x24 -nolisten tcp >/tmp/did-xvfb.log 2>&1 &
fi
exec "$@"
