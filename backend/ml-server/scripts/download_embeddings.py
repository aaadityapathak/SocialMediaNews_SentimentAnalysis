from pathlib import Path

from huggingface_hub import snapshot_download

REPO = "sentence-transformers/all-mpnet-base-v2"
OUT = Path(__file__).resolve().parents[1] / "hf-models" / "embeddings"

# Only fetch what the SentenceTransformer ONNX backend needs; skip safetensors,
# pytorch_model.bin, tf weights, and unused ONNX variants to keep the artifact small.
ALLOW_PATTERNS = [
    "config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "vocab.txt",
    "sentence_bert_config.json",
    "config_sentence_transformers.json",
    "modules.json",
    "1_Pooling/config.json",
    "onnx/model_qint8_avx512_vnni.onnx",
]

if __name__ == "__main__":
    snapshot_download(
        repo_id=REPO, local_dir=OUT, allow_patterns=ALLOW_PATTERNS
    )
    print(f"Embeddings model saved to {OUT}")
