from setuptools import find_packages, setup

package_name = 'digital_twin_guard'
setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', ['launch/poc.launch.py']),
        ('share/' + package_name + '/config', ['config/experiment.yaml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Romulo Nayrod Villa Munoz',
    maintainer_email='nayrodvilla@kduniv.ac.kr',
    description='Research prototype for digital-twin-supported GNSS spoofing screening in PX4 SITL.',
    license='Apache-2.0',
    entry_points={'console_scripts': ['detector = digital_twin_guard.detector_node:main']},
)
