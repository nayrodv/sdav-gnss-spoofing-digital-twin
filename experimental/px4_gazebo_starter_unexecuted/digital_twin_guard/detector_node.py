#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy
from px4_msgs.msg import SensorGps, VehicleLocalPosition
from std_msgs.msg import String

from .core import DetectorConfig, ResidualSpoofingDetector

EARTH_RADIUS_M = 6378137.0


class DigitalTwinGuardNode(Node):
    """PX4 ROS 2 research node for residual-based GNSS spoofing screening.

    Subscribes to the default PX4 DDS topics exposed for raw GPS and fused local
    position. It maintains a short-horizon constant-velocity predictor and emits
    a structured alert. It deliberately does not command the flight controller.
    """

    def __init__(self):
        super().__init__('digital_twin_guard')
        self.declare_parameter('minimum_threshold_m', 5.0)
        self.declare_parameter('persistence_samples', 8)
        self.declare_parameter('baseline_samples', 200)
        cfg = DetectorConfig(
            minimum_threshold_m=float(self.get_parameter('minimum_threshold_m').value),
            persistence_samples=int(self.get_parameter('persistence_samples').value),
            baseline_samples=int(self.get_parameter('baseline_samples').value),
        )
        self.detector = ResidualSpoofingDetector(cfg)
        qos = QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT,
                         durability=DurabilityPolicy.VOLATILE,
                         history=HistoryPolicy.KEEP_LAST, depth=10)
        self.gps = None
        self.local = None
        self.ref_lat = None
        self.ref_lon = None
        self.pred_n = None
        self.pred_e = None
        self.last_local_time = None
        self.create_subscription(SensorGps, '/fmu/out/vehicle_gps_position', self.on_gps, qos)
        self.create_subscription(VehicleLocalPosition, '/fmu/out/vehicle_local_position', self.on_local, qos)
        self.pub = self.create_publisher(String, '/digital_twin_guard/anomaly', 10)
        self.timer = self.create_timer(0.1, self.evaluate)

    def on_gps(self, msg: SensorGps):
        self.gps = msg
        if self.ref_lat is None and msg.lat != 0 and msg.lon != 0:
            self.ref_lat = msg.lat * 1e-7
            self.ref_lon = msg.lon * 1e-7

    def on_local(self, msg: VehicleLocalPosition):
        now = time.monotonic()
        if self.pred_n is None:
            self.pred_n, self.pred_e = float(msg.x), float(msg.y)
        elif self.last_local_time is not None:
            dt = max(0.0, min(0.5, now - self.last_local_time))
            if math.isfinite(msg.vx) and math.isfinite(msg.vy):
                self.pred_n += float(msg.vx) * dt
                self.pred_e += float(msg.vy) * dt
            self.pred_n = 0.98 * self.pred_n + 0.02 * float(msg.x)
            self.pred_e = 0.98 * self.pred_e + 0.02 * float(msg.y)
        self.local = msg
        self.last_local_time = now

    def gps_to_ne(self):
        lat = self.gps.lat * 1e-7
        lon = self.gps.lon * 1e-7
        dlat = math.radians(lat - self.ref_lat)
        dlon = math.radians(lon - self.ref_lon)
        n = EARTH_RADIUS_M * dlat
        e = EARTH_RADIUS_M * math.cos(math.radians(self.ref_lat)) * dlon
        return n, e

    def evaluate(self):
        if self.gps is None or self.local is None or self.ref_lat is None or self.pred_n is None:
            return
        gps_n, gps_e = self.gps_to_ne()
        age_s = max(0.0, (self.get_clock().now().nanoseconds / 1e3 - float(self.gps.timestamp)) / 1e6)
        out = self.detector.update(gps_n, gps_e, self.pred_n, self.pred_e, age_s)
        payload = {
            'timestamp_us': int(self.gps.timestamp),
            'residual_m': round(out.residual_m, 3),
            'threshold_m': round(out.threshold_m, 3),
            'persistence_count': out.persistent_count,
            'suspected_spoofing': out.suspected,
            'recovered': out.recovered,
            'message_age_s': round(age_s, 3),
            'recommended_next_step': 'increase verification / isolate GNSS only after assurance gating' if out.suspected else 'monitor',
        }
        msg = String()
        msg.data = json.dumps(payload)
        self.pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = DigitalTwinGuardNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
