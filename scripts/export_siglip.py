#!/usr/bin/env python3
"""
Export google/siglip2-so400m-patch14-384 vision encoder to ONNX.

This script downloads the SigLIP 2 model from HuggingFace and exports
only the vision encoder to ONNX format for use in the similarity system.

Usage:
    python scripts/export_siglip.py
    
Requires:
    pip install transformers torch optimum onnx onnxruntime
"""
import os
import sys
from pathlib import Path

# Add parent directory to path for config import
sys.path.insert(0, str(Path(__file__).parent.parent))

MODEL_ID = "google/siglip2-so400m-patch14-384"
OUTPUT_DIR = Path(__file__).parent.parent / "models" / "SigLIP"
OUTPUT_PATH = OUTPUT_DIR / "model.onnx"


def export_vision_encoder():
    """Export only the vision encoder portion of SigLIP to ONNX."""
    print("=" * 70)
    print("SigLIP 2 Vision Encoder Export")
    print("=" * 70)
    print(f"Model: {MODEL_ID}")
    print(f"Output: {OUTPUT_PATH}")
    print()
    
    # Check if already exists
    if OUTPUT_PATH.exists():
        response = input("Model already exists. Overwrite? [y/N]: ")
        if response.lower() not in ['y', 'yes']:
            print("Aborted.")
            return False
    
    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print("Loading model from HuggingFace...")
    try:
        import torch
        from transformers import AutoModel, AutoImageProcessor
    except ImportError:
        print("ERROR: Please install transformers and torch:")
        print("  pip install transformers torch")
        return False
    
    # Load the full model
    model = AutoModel.from_pretrained(MODEL_ID, trust_remote_code=True)
    # Only load image processor (not full processor which needs tokenizer)
    image_processor = AutoImageProcessor.from_pretrained(MODEL_ID, trust_remote_code=True)
    
    # Get just the vision model
    vision_model = model.vision_model
    vision_model.eval()
    
    print(f"Model loaded. Vision encoder config:")
    print(f"  Hidden size: {vision_model.config.hidden_size}")
    print(f"  Image size: {vision_model.config.image_size}")
    print()
    
    # Create dummy input for tracing
    # SigLIP expects pixel_values in NCHW format
    image_size = vision_model.config.image_size
    dummy_input = torch.randn(1, 3, image_size, image_size)
    
    print("Exporting to ONNX...")
    try:
        torch.onnx.export(
            vision_model,
            (dummy_input,),
            str(OUTPUT_PATH),
            input_names=['pixel_values'],
            output_names=['pooler_output', 'last_hidden_state'],
            dynamic_axes={
                'pixel_values': {0: 'batch_size'},
                'pooler_output': {0: 'batch_size'},
                'last_hidden_state': {0: 'batch_size'},
            },
            opset_version=17,
            do_constant_folding=True,
        )
    except Exception as e:
        print(f"Standard export failed: {e}")
        print("Trying simplified export...")
        
        # Some models need a wrapper to get clean output
        class VisionEncoderWrapper(torch.nn.Module):
            def __init__(self, vision_model):
                super().__init__()
                self.vision_model = vision_model
                
            def forward(self, pixel_values):
                outputs = self.vision_model(pixel_values)
                # Return the pooled output (1152-d embedding)
                return outputs.pooler_output
        
        wrapped_model = VisionEncoderWrapper(vision_model)
        wrapped_model.eval()
        
        torch.onnx.export(
            wrapped_model,
            (dummy_input,),
            str(OUTPUT_PATH),
            input_names=['pixel_values'],
            output_names=['embedding'],
            dynamic_axes={
                'pixel_values': {0: 'batch_size'},
                'embedding': {0: 'batch_size'},
            },
            opset_version=17,
            do_constant_folding=True,
        )
    
    print(f"✓ Exported to {OUTPUT_PATH}")
    
    # Verify the output
    print("\nVerifying ONNX model...")
    try:
        import onnxruntime as ort
        import numpy as np
        
        session = ort.InferenceSession(str(OUTPUT_PATH))
        
        # Get input/output info
        input_info = session.get_inputs()[0]
        output_info = session.get_outputs()
        
        print(f"  Input: {input_info.name} {input_info.shape}")
        for out in output_info:
            print(f"  Output: {out.name} {out.shape}")
        
        # Test inference
        test_input = np.random.randn(1, 3, image_size, image_size).astype(np.float32)
        outputs = session.run(None, {input_info.name: test_input})
        
        # Find the embedding output (should be 1152-d)
        for i, out in enumerate(outputs):
            out_flat = out.flatten() if len(out.shape) > 2 else out[0] if len(out.shape) == 2 else out
            print(f"  Output {i} shape: {out.shape}, flattened size: {len(out_flat)}")
        
        print("\n✓ ONNX model verification passed!")
        
    except ImportError:
        print("  (Skipping verification - onnxruntime not installed)")
    except Exception as e:
        print(f"  WARNING: Verification failed: {e}")
        print("  The model may still work, but please test manually.")
    
    # Save processor config for reference
    config_path = OUTPUT_DIR / "config.json"
    try:
        import json
        config_data = {
            "model_id": MODEL_ID,
            "image_size": image_size,
            "hidden_size": vision_model.config.hidden_size,
            "notes": "SigLIP expects [0,1] normalized RGB, no ImageNet mean/std subtraction"
        }
        with open(config_path, 'w') as f:
            json.dump(config_data, f, indent=2)
        print(f"✓ Saved config to {config_path}")
    except Exception as e:
        print(f"  (Could not save config: {e})")
    
    print("\n" + "=" * 70)
    print("Export complete!")
    print("=" * 70)
    return True


if __name__ == "__main__":
    success = export_vision_encoder()
    sys.exit(0 if success else 1)
