import cv2
import time
import numpy as np
import HandTrackingModule as htm
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
import screen_brightness_control as sbc

# Camera resolution
wCam, hCam = 640, 480

cap = cv2.VideoCapture(0)
if not cap.isOpened():
    raise RuntimeError("Cannot open camera 0")
cap.set(3, wCam)
cap.set(4, hCam)
pTime = 0

# Initialize the hand detector
detector = htm.handDetector(detectionCon=0.7, maxHands=1)

# Access the system volume interface
# Works with both old pycaw (IMMDevice.Activate) and new pycaw (AudioDevice.EndpointVolume)
devices = AudioUtilities.GetSpeakers()
if hasattr(devices, "EndpointVolume"):
    volume = devices.EndpointVolume
else:
    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    volume = cast(interface, POINTER(IAudioEndpointVolume))
volRange = volume.GetVolumeRange()
minVol = volRange[0]
maxVol = volRange[1]

volBar = 400
volPer = 0
colorVol = (255, 0, 0)
lastVolSet = -1

# Brightness variables
brightBar = 400
brightPer = 0
colorBright = (0, 255, 255)
lastBrightSet = -1

# Pinch ratio (distance / hand width) mapped to 0-100%
PINCH_RANGE = [0.15, 0.75]

# Exit gesture: index+middle+ring straight, thumb and pinky touching
EXIT_PINCH_RATIO = 0.35
EXIT_HOLD_FRAMES = 5
exitHold = 0


def get_current_volume():
    try:
        return int(volume.GetMasterVolumeLevelScalar() * 100)
    except Exception:
        return -1


def get_current_brightness():
    try:
        b = sbc.get_brightness()
        if isinstance(b, list):
            return int(b[0]) if b else -1
        return int(b)
    except Exception:
        return -1


while True:
    success, img = cap.read()
    if not success or img is None:
        print("Camera read failed")
        break

    img = detector.findHands(img)
    lmList, bbox = detector.findPosition(img, draw=True)

    if len(lmList) != 0 and len(bbox) == 4:
        area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]) // 100

        if 250 < area < 1000:
            fingers = detector.fingersUp()
            handWidth = bbox[2] - bbox[0]

            # Volume: thumb + index only
            if fingers == [1, 1, 0, 0, 0] and handWidth > 0:
                lengthVol, img, lineInfoVol = detector.findDistance(4, 8, img, draw=False)

                normLengthVol = np.interp(lengthVol / handWidth, PINCH_RANGE, [0, 100])
                volBar = np.interp(normLengthVol, [0, 100], [400, 150])
                volPer = np.interp(normLengthVol, [0, 100], [0, 100])

                if abs(volPer - lastVolSet) >= 2:
                    volume.SetMasterVolumeLevelScalar(volPer / 100, None)
                    lastVolSet = volPer

                cv2.circle(img, (lineInfoVol[4], lineInfoVol[5]), 15, (0, 255, 0), cv2.FILLED)
                colorVol = (0, 255, 0)
            else:
                colorVol = (255, 0, 0)

            # Brightness: thumb + index + middle only
            if fingers == [1, 1, 1, 0, 0] and handWidth > 0:
                lengthBright, img, lineInfoBright = detector.findDistance(4, 12, img, draw=False)

                normLengthBright = np.interp(lengthBright / handWidth, PINCH_RANGE, [0, 100])
                brightBar = np.interp(normLengthBright, [0, 100], [400, 150])
                brightPer = np.interp(normLengthBright, [0, 100], [0, 100])

                if abs(brightPer - lastBrightSet) >= 2:
                    sbc.set_brightness(int(round(brightPer)))
                    lastBrightSet = brightPer

                cv2.circle(img, (lineInfoBright[4], lineInfoBright[5]), 15, (0, 255, 255), cv2.FILLED)
                colorBright = (0, 255, 255)
            else:
                colorBright = (0, 255, 255) if fingers == [0, 0, 0, 0, 0] else (255, 0, 0)

            # Exit: index+middle+ring straight, thumb tip touching pinky tip
            if fingers[1] == 1 and fingers[2] == 1 and fingers[3] == 1 and handWidth > 0:
                tipDist, img, lineInfoExit = detector.findDistance(4, 20, img, draw=False)
                if tipDist / handWidth < EXIT_PINCH_RATIO:
                    exitHold += 1
                    cv2.circle(img, (lineInfoExit[4], lineInfoExit[5]), 25, (0, 0, 255), cv2.FILLED)
                    cv2.putText(img, f'EXIT {exitHold}/{EXIT_HOLD_FRAMES}', (400, 150),
                                cv2.FONT_HERSHEY_COMPLEX, 1, (0, 0, 255), 3)
                else:
                    exitHold = 0
            else:
                exitHold = 0

    # Volume bar
    cv2.rectangle(img, (50, 150), (85, 400), (255, 0, 0), 3)
    cv2.rectangle(img, (50, int(volBar)), (85, 400), (255, 0, 0), cv2.FILLED)
    cv2.putText(img, f'{int(volPer)} %', (40, 450), cv2.FONT_HERSHEY_COMPLEX, 1, (255, 0, 0), 3)
    cVol = get_current_volume()
    if cVol >= 0:
        cv2.putText(img, f'Vol Set: {cVol}', (400, 50), cv2.FONT_HERSHEY_COMPLEX, 1, colorVol, 3)

    # Brightness bar
    cv2.rectangle(img, (100, 150), (135, 400), (0, 255, 255), 3)
    cv2.rectangle(img, (100, int(brightBar)), (135, 400), (0, 255, 255), cv2.FILLED)
    cv2.putText(img, f'{int(brightPer)} %', (90, 450), cv2.FONT_HERSHEY_COMPLEX, 1, (0, 255, 255), 3)
    curBright = get_current_brightness()
    if curBright >= 0:
        cv2.putText(img, f'Bright: {curBright}%', (400, 100), cv2.FONT_HERSHEY_COMPLEX, 1, colorBright, 3)

    # Frame rate
    cTime = time.time()
    fps = 1 / (cTime - pTime) if cTime > pTime else 0
    pTime = cTime
    cv2.putText(img, f'FPS: {int(fps)}', (40, 50), cv2.FONT_HERSHEY_COMPLEX, 1, (255, 0, 0), 3)

    cv2.imshow("Img", img)
    if cv2.waitKey(1) & 0xFF == ord('q') or exitHold >= EXIT_HOLD_FRAMES:
        break

cap.release()
cv2.destroyAllWindows()
