from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package='digital_twin_guard', executable='detector', output='screen',
            parameters=['config/experiment.yaml']
        )
    ])
