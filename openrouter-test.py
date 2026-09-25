# test_openrouter.py
import sys
from PySide6.QtWidgets import QApplication
from api.openrouter_client import OpenRouterImageWorker
from config import load_settings, IMAGES_DIR

app = QApplication(sys.argv)
settings = load_settings()

worker = OpenRouterImageWorker(
    api_key=settings["openrouter_api_key"],
    model=settings["openrouter_image_model"],
    prompt="A cozy reading nook with warm lighting, digital art",
    save_dir=str(IMAGES_DIR),
)
worker.image_ready.connect(lambda path: (print("Saved:", path), app.quit()))
worker.error.connect(lambda msg: (print("Error:", msg), app.quit()))
worker.start()
sys.exit(app.exec())