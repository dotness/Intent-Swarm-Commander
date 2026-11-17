#!/bin/bash
source /opt/ros/humble/setup.bash

# Start XRCE-DDS Bridge in the background
MicroXRCEAgent udp4 -p 8888 &

# Start PX4 and Gazebo in headless CPU mode
cd /opt/PX4-Autopilot
HEADLESS=1 make px4_sitl sihsim_quadx
