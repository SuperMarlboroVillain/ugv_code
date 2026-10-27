#!/usr/bin/env python3
# OPENCV 模式实验入口：USB 广角相机 640x480 取流 + HSV 颜色识别 + 本地预览窗口。
# 对应 PRD FR-08 规则1：独立预览窗口、叠加识别框与参数、阈值现场可调即时生效。
# 键位: r/g/b/y 预设色(红自动叠加 170-180 环绕区间) | q 退出
# 运行: ~/ugv_ros.sh python3 /home/ws/ugv_ws/opencv_color_lab.py
import cv2
import numpy as np

# 注意: 窗口标题必须 ASCII——容器内 OpenCV Qt 后端对中文标题的 trackbar 查找有 bug
# （窗口能建但 createTrackbar 报 NULL window handler），换任何 locale 都无效。
WIN = "OpenCV Color Lab  (q quit | r/g/b/y preset)"
PRESETS = {
    'r': (0, 120, 70, 10, 255, 255),
    'g': (35, 80, 80, 85, 255, 255),
    'b': (100, 120, 70, 130, 255, 255),
    'y': (20, 120, 120, 40, 255, 255),
}
cur = 'r'
# (名称, 在 PRESETS 六元组中的下标, 最大值)；'min area' 无对应下标
TBARS = [('H low', 0, 180), ('H high', 3, 180),
         ('S low', 1, 255), ('S high', 4, 255),
         ('V low', 2, 255), ('V high', 5, 255),
         ('min area', None, 5000)]


def set_trackbars(p):
    for name, idx, _ in TBARS:
        if idx is not None:
            cv2.setTrackbarPos(name, WIN, p[idx])


def get_ranges():
    g = lambda n: cv2.getTrackbarPos(n, WIN)
    r = [(g('H low'), g('S low'), g('V low'), g('H high'), g('S high'), g('V high'))]
    if cur == 'r':
        r.append((170, 120, 70, 180, 255, 255))  # 红色色相环绕区间
    return r


cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
if not cap.isOpened():
    raise SystemExit("!! 打不开 /dev/video0（检查相机USB/是否被占用，先切 OPENCV 模式）")
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
for _ in range(10):
    cap.read()
ok, first = cap.read()
if not ok:
    raise SystemExit("!! 读不到图像（相机已掉线？）")
cv2.namedWindow(WIN)
cv2.imshow(WIN, first)
# QT 后端需先显示一次才真正建窗，否则 createTrackbar 报 NULL window handler
cv2.waitKey(1)
for name, idx, maxv in TBARS:
    cv2.createTrackbar(name, WIN, PRESETS[cur][idx] if idx is not None else 300, maxv, lambda *_: None)

kernel = np.ones((5, 5), np.uint8)
while True:
    ok, frame = cap.read()
    if not ok:
        continue
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = None
    for lo_h, lo_s, lo_v, hi_h, hi_s, hi_v in get_ranges():
        m = cv2.inRange(hsv, (lo_h, lo_s, lo_v), (hi_h, hi_s, hi_v))
        mask = m if mask is None else mask | m
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    n, labels, stats, cent = cv2.connectedComponentsWithStats(mask)
    min_area = cv2.getTrackbarPos('min area', WIN)
    idx, best = 0, 0
    for i in range(1, n):
        a = stats[i, cv2.CC_STAT_AREA]
        if a >= min_area and a > best:
            best, idx = a, i
    if idx:
        x, y, w, h, area = stats[idx]
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
        cv2.putText(frame, f"area={area}px ({area*100.0/(640*480):.1f}%)",
                    (x, max(20, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        cv2.circle(frame, (int(cent[idx][0]), int(cent[idx][1])), 4, (0, 0, 255), -1)
    vis = cv2.hconcat([frame, cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)])
    cv2.imshow(WIN, vis)
    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        break
    if chr(key) in PRESETS and chr(key) != cur:
        cur = chr(key)
        set_trackbars(PRESETS[cur])

cap.release()
cv2.destroyAllWindows()
