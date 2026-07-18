# Deep Learning Models for VQ-Vision

This directory stores the pre-trained weights (`.pth`, `.h5`) for the solar detection models.

## Usage
1. Train the U-Net model using the `train.py` script (not included in this demo).
2. Save the best checkpoint as `best_model.pth`.
3. Place the file in this directory.
4. The backend service will automatically load it for high-precision inference.

## Current Architecture
- **Model**: U-Net (ResNet34 Backbone)
- **Input**: Sentinel-2 10m bands (R, G, B, NIR)
- **Output**: Binary Mask (Solar Panel / Background)
- **Method**: VQ-Clustering assisted supervision.

## Files
- `unet.py`: Model definition.
- `inference.py`: Helper script for running detection on local images.
