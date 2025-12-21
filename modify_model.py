
import onnx

model_path = "/mnt/Server/ChibiBooru/models/Similarity/model.onnx"
model = onnx.load(model_path)

# Nodes to expose
# 1. GAP output (raw features)
gap_node_name = 'StatefulPartitionedCall/ConvNextBV1/predictions_globalavgpooling/Mean:0'
# 2. Normalized output (before classifier)
norm_node_name = 'StatefulPartitionedCall/ConvNextBV1/predictions_norm/add:0'

# Helper to add output
def add_output(model, tensor_name):
    # Check if already in outputs
    for output in model.graph.output:
        if output.name == tensor_name:
            print(f"Output {tensor_name} already exists.")
            return

    # Find the value info for this tensor (if available) or create it
    # Since we might not know the shape/type easily without shape inference, 
    # we can try to add it with minimal info or simply append to output and let runtime handle it?
    # ONNX requirement: Output must have type info.
    # We can infer shapes.
    
    # Create a ValueInfoProto
    # We assume float, finding shape via inference is best but we can try adding without shape? 
    # onnx.helper.make_tensor_value_info requires shape.
    pass

# We will use onnx.utils.extract_model to create a new model with these outputs? 
# Or just append to graph.output and run shape inference.

from onnx import helper, shape_inference

# Add the intermediate tensors to the graph's output fields
# We need to know the type. It is float (1).
# We guess the shape is [batch, 1024].
gap_output = helper.make_tensor_value_info(gap_node_name, onnx.TensorProto.FLOAT, ['batch_size', 1024])
norm_output = helper.make_tensor_value_info(norm_node_name, onnx.TensorProto.FLOAT, ['batch_size', 1024])

model.graph.output.append(gap_output)
model.graph.output.append(norm_output)

# Save
onnx.save(model, model_path)
print(f"Modified model saved to {model_path}")
