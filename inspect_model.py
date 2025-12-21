
import onnxruntime as ort
import sys
import os

model_path = "/mnt/Server/ChibiBooru/models/Similarity/model.onnx"

if not os.path.exists(model_path):
    print(f"Model not found at {model_path}")
    sys.exit(1)

try:
    session = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])
    print("Model Inputs:")
    for i in session.get_inputs():
        print(f"  Name: {i.name}, Shape: {i.shape}, Type: {i.type}")

    print("\nModel Outputs:")
    for i in session.get_outputs():
        print(f"  Name: {i.name}, Shape: {i.shape}, Type: {i.type}")

except Exception as e:
    print(f"Error loading model: {e}")
