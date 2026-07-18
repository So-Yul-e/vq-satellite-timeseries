import torch
import sys
import os

# Add backend path to sys.path to import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.ml.unet import UNet

def create_dummy_weights():
    # 4 bands input (R, G, B, NIR) -> 2 classes output
    model = UNet(n_channels=3, n_classes=2)
    
    # Save dummy weights
    save_path = os.path.join(os.path.dirname(__file__), 'best_model.pth')
    torch.save(model.state_dict(), save_path)
    print(f"✅ Dummy weights saved to {save_path}")

if __name__ == "__main__":
    create_dummy_weights()
