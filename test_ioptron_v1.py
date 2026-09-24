#!/usr/bin/env python3
"""
Test script to capture a frame from the iOptron iPolar UVC device on video1
"""
import sys
import cv2
import numpy as np

def test_ioptron():
    print("Testing iOptron iPolar UVC device on /dev/video1...")
    
    # Try to open the video device
    cap = cv2.VideoCapture(1)  # /dev/video1
    
    if not cap.isOpened():
        print("Failed to open /dev/video1")
        return False
    else:
        print("Opened /dev/video1")
    
    # Get device properties
    width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
    height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    fps = cap.get(cv2.CAP_PROP_FPS)
    format = cap.get(cv2.CAP_PROP_FORMAT)
    
    print(f"Device properties:")
    print(f"  Resolution: {width}x{height}")
    print(f"  FPS: {fps}")
    print(f"  Format: {format}")
    
    # Try to capture a frame
    print("Attempting to capture frame...")
    ret, frame = cap.read()
    
    if ret:
        print(f"Successfully captured frame! Shape: {frame.shape}")
        print(f"Frame dtype: {frame.dtype}")
        
        # Save the frame as an image
        cv2.imwrite('/tmp/ioptrom_test_frame_v1.png', frame)
        print("Saved frame to /tmp/ioptrom_test_frame_v1.png")
        
        # Show some basic stats
        print(f"Min pixel value: {frame.min()}")
        print(f"Max pixel value: {frame.max()}")
        print(f"Mean pixel value: {frame.mean():.2f}")
        
    else:
        print("Failed to capture frame")
    
    # Clean up
    cap.release()
    return ret

if __name__ == "__main__":
    try:
        success = test_ioptron()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)