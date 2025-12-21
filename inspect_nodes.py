
import onnx

model_path = "/mnt/Server/ChibiBooru/models/Similarity/model.onnx"
model = onnx.load(model_path)

print("Nodes related to pooling or output:")
for node in model.graph.node:
    if "pool" in node.name.lower() or "gemm" in node.op_type.lower() or "matmul" in node.op_type.lower():
        print(f"Name: {node.name}, Op: {node.op_type}, Output: {node.output}")

print("\nLast 10 nodes:")
for node in model.graph.node[-10:]:
    print(f"Name: {node.name}, Op: {node.op_type}, Output: {node.output}")
