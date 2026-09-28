import cv2
print("OpenCV version:", cv2.__version__)
# Try to open the device with V4L2 backend
cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
if not cap.isOpened():
    print("Failed to open /dev/video0 with V4L2 backend")
    # Try video1
    cap = cv2.VideoCapture(1, cv2.CAP_V4L2)
    if not cap.isOpened():
        print("Failed to open /dev/video1 with V4L2 backend")
    else:
        print("Opened /dev/video1 with V4L2 backend")
else:
    print("Opened /dev/video0 with V4L2 backend")

if cap.isOpened():
    ret, frame = cap.read()
    if ret:
        print("Frame captured successfully!")
        print("Frame shape:", frame.shape)
        # Save the frame to a file for verification
        cv2.imwrite('test_frame.jpg', frame)
        print("Frame saved as test_frame.jpg")
    else:
        print("Failed to capture frame")
    cap.release()
else:
    print("Cannot proceed without an open camera")
