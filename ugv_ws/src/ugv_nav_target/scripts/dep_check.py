import sys
import traceback

results = []

def check(name, fn):
    try:
        fn()
        results.append(f"OK   {name}")
    except Exception:
        results.append(f"FAIL {name}")
        results.append(traceback.format_exc(limit=2))

def t_cv2():
    import cv2
    import numpy
    assert cv2.__version__ == "4.11.0", cv2.__version__
    img = numpy.zeros((10, 10, 3), dtype=numpy.uint8)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    assert hsv.shape == (10, 10, 3)

def t_numpy():
    import numpy
    assert numpy.__version__ == "1.26.4", numpy.__version__

def t_cvbridge():
    from cv_bridge import CvBridge
    b = CvBridge()
    assert b is not None

def t_tf2():
    import tf2_geometry_msgs  # noqa: F401

def t_rclpy():
    import rclpy
    assert rclpy.ok() is False or True

for name, fn in [
    ("numpy==1.26.4", t_numpy),
    ("opencv 4.11 + cvtColor", t_cv2),
    ("cv_bridge", t_cvbridge),
    ("tf2_geometry_msgs", t_tf2),
    ("rclpy", t_rclpy),
]:
    check(name, fn)

with open("/tmp/dep_check_result.txt", "w") as f:
    f.write("\n".join(results) + "\n")
print("DONE")
