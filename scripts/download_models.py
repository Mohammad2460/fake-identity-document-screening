"""One-time download of the face ONNX models. Requires network; run during setup only."""
import os
import urllib.request

MODELS = {
    "face_detection_yunet_2023mar.onnx":
        "https://github.com/opencv/opencv_zoo/raw/main/models/"
        "face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "face_recognition_sface_2021dec.onnx":
        "https://github.com/opencv/opencv_zoo/raw/main/models/"
        "face_recognition_sface/face_recognition_sface_2021dec.onnx",
}

def main() -> None:
    os.makedirs("models", exist_ok=True)
    for name, url in MODELS.items():
        dest = os.path.join("models", name)
        if os.path.exists(dest):
            print(f"[skip] {name}")
            continue
        print(f"[get ] {name}")
        urllib.request.urlretrieve(url, dest)
        print(f"[ok  ] {name} ({os.path.getsize(dest) // 1024} KB)")

if __name__ == "__main__":
    main()
