import cv2
import numpy as np
from insightface.app import FaceAnalysis
import os

def test_face():
    print("Initializing FaceAnalysis...")
    try:
        app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        app.prepare(ctx_id=0)
        print("✓ FaceAnalysis initialized successfully")
        
        # Create a dummy image with a face (or just a black image)
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        faces = app.get(img)
        print(f"✓ app.get() worked (detected {len(faces)} faces in black image)")
        
    except Exception as e:
        print(f"✗ Error: {e}")

if __name__ == "__main__":
    test_face()
