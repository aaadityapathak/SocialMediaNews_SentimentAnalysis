from pathlib import Path

from optimum.onnxruntime import ORTModelForSequenceClassification
from onnxruntime.quantization import quantize_dynamic, QuantType
from transformers import AutoTokenizer

REPO = "cardiffnlp/twitter-roberta-base-emotion-latest"
OUT = Path(__file__).resolve().parents[1] / "hf-models" / "emotion"
OUT.mkdir(parents=True, exist_ok=True)

FP32 = OUT / "model_fp32.onnx"
QUANTIZED = OUT / "model.onnx"

if __name__ == "__main__":
    print("Exporting emotion detection model to ONNX...")
    model = ORTModelForSequenceClassification.from_pretrained(REPO, export=True)

    # save_pretrained writes model.onnx; rename it so we can write the quantized version there
    model.save_pretrained(OUT)
    (OUT / "model.onnx").rename(FP32)

    print("Saving tokenizer...")
    AutoTokenizer.from_pretrained(REPO).save_pretrained(OUT)

    print("Quantizing to int8...")
    quantize_dynamic(
        model_input=str(FP32),
        model_output=str(QUANTIZED),
        weight_type=QuantType.QInt8,
    )
    FP32.unlink()

    print(f"Emotion model saved to {OUT}")
