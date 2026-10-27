from setuptools import setup
import os
from glob import glob

package_name = 'ugv_auto'

setup(
    name=package_name,
    version='1.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
        (os.path.join('share', package_name, 'scripts'), glob('scripts/*.sh')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='ugv_project',
    maintainer_email='ugv@project.local',
    description='UGV Beast 一体式项目包：建图/导航/视觉识别整合',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'mono_detector = ugv_auto.mono_detector:main',
            'approach_manager = ugv_auto.approach_manager:main',
            'joy_teleop = ugv_auto.joy_teleop:main',
            'keyboard_teleop = ugv_auto.keyboard_teleop:main',
            'cmd_vel_watchdog = ugv_auto.cmd_vel_watchdog:main',
        ],
    },
)
