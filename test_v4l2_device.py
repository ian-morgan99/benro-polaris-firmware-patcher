import cv2
print("OpenCV version:", cv2.__version__)

# Try to open the device by device node
cap = cv2.VideoCapture('/dev/video0', cv2.CAP_V4L2)
if not cap.isOpened():
    print("Failed to open /dev/video0 by device node with V4L2 backend")
    # Try video1
    cap = cv2.VideoCapture('/dev/video1', cv2.CAP_V4L2)
    if not cap.isOpened():
        print("Failed to open /dev/video1 by device node with V4L2 backend")
    else:
        print("Opened /dev/video1 by device node with V4L2 backend")
else:
    print("Opened /dev/video0 by device node with V4L2 backend")

if cap.isOpened():
    # Try to set format to MJPG (common for UVC)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    
    # Get the actual settings
    width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
    height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    fps = cap.get(cv2.CAP_PROP_FPS)
    fourcc = cap.get(cv2.CAP_PROP_FOURCC)
    print(f"Set resolution: {width}x{height}")
    print(f"FPS: {fps}")
    print(f"FourCC: {fourcc}")
    
    ret, frame = cap.read()
    if ret:
        print("Frame captured successfully!")
        print("Frame shape:", frame.shape)
        cv2.imwrite('test_frame.jpg', frame)
        print("Frame saved as test_frame.jpg")
    else:
        print("Failed to capture frame")
    cap.release()
else:
    print("Cannot proceed without an open camera")
