#!/bin/bash
source /opt/ros/humble/setup.bash

# Start XRCE-DDS Bridge in the background
MicroXRCEAgent udp4 -p 8888 &

# Start PX4 and Gazebo in the foreground
cd /opt/PX4-Autopilot
make px4_sitl gz_x500
