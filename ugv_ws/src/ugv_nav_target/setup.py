import os
from glob import glob

from setuptools import setup

package_name = "ugv_nav_target"

setup(
    name=package_name,
    version="1.0.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "launch"), glob("launch/*.launch.py")),
        (os.path.join("share", package_name, "config"), glob("config/*.yaml")),
        (os.path.join("share", package_name, "scripts"), glob("scripts/*.sh")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    description="UGV Beast 自主导航 + OpenCV 目标识别",
    license="MIT",
    entry_points={
        "console_scripts": [
            "target_detector = ugv_nav_target.target_detector:main",
            "goal_sender = ugv_nav_target.goal_sender:main",
        ],
    },
)
