import cv2

print("Scanning for connected cameras...\n")

found_cameras = False

for i in range(5):
    cap = cv2.VideoCapture(i)
    if cap.isOpened():
        ret, frame = cap.read()
        if ret and frame is not None:
            print(f"✅ SUCCESS: Camera found at index {i}")
            found_cameras = True
            
            # Show the camera feed
            cv2.putText(frame, f"This is Camera Index: {i}", (10, 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            cv2.putText(frame, "Press ANY KEY on your keyboard to test the next one", (10, 70), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            
            cv2.imshow(f"Testing Camera {i}", frame)
            
            # Wait until you press a key, then close the window and check the next index
            cv2.waitKey(0) 
            cv2.destroyAllWindows()
        else:
            print(f"⚠️ WARNING: Index {i} exists, but the screen is totally black.")
    else:
        print(f"❌ No camera detected at index {i}")
        
    cap.release()

print("\nScan complete!")