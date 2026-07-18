"""U-Net++ 학습 메인 스크립트"""
import sys
import os
from pathlib import Path

# src 경로 추가
sys.path.append(str(Path(__file__).parent / 'src'))

import torch
import torch.nn as nn
import torch.optim as optim
from torch.optim.lr_scheduler import ReduceLROnPlateau, CosineAnnealingLR
import argparse
from datetime import datetime

from models.unet_plusplus import create_solar_panel_model
from training.dataset import create_dataloaders
from training.losses import CombinedLoss
from training.trainer import Trainer


def parse_args():
    parser = argparse.ArgumentParser(description='Train U-Net++ for Solar Panel Detection')

    # 데이터
    parser.add_argument('--train-images', type=str, required=True,
                        help='Training images directory')
    parser.add_argument('--train-masks', type=str, required=True,
                        help='Training masks directory')
    parser.add_argument('--val-images', type=str, required=True,
                        help='Validation images directory')
    parser.add_argument('--val-masks', type=str, required=True,
                        help='Validation masks directory')

    # 모델
    parser.add_argument('--use-nir', action='store_true',
                        help='Use NIR channel (4 input channels)')
    parser.add_argument('--base-channels', type=int, default=64,
                        help='Base channels for U-Net++')
    parser.add_argument('--use-attention', action='store_true', default=True,
                        help='Use attention mechanism')

    # 학습
    parser.add_argument('--epochs', type=int, default=100,
                        help='Number of training epochs')
    parser.add_argument('--batch-size', type=int, default=8,
                        help='Batch size')
    parser.add_argument('--lr', type=float, default=1e-4,
                        help='Learning rate')
    parser.add_argument('--weight-decay', type=float, default=1e-5,
                        help='Weight decay')
    parser.add_argument('--early-stopping', type=int, default=15,
                        help='Early stopping patience')

    # Loss
    parser.add_argument('--bce-weight', type=float, default=0.5,
                        help='BCE loss weight')
    parser.add_argument('--dice-weight', type=float, default=0.5,
                        help='Dice loss weight')
    parser.add_argument('--use-focal', action='store_true',
                        help='Use Focal Loss instead of BCE')

    # 기타
    parser.add_argument('--image-size', type=int, default=256,
                        help='Image size (square)')
    parser.add_argument('--num-workers', type=int, default=4,
                        help='Number of data loader workers')
    parser.add_argument('--device', type=str, default='cuda',
                        choices=['cuda', 'cpu'],
                        help='Device to use')
    parser.add_argument('--checkpoint-dir', type=str, default='checkpoints',
                        help='Checkpoint directory')
    parser.add_argument('--log-dir', type=str, default='logs',
                        help='Log directory')
    parser.add_argument('--resume', type=str, default=None,
                        help='Resume from checkpoint')

    return parser.parse_args()


def main():
    args = parse_args()

    # Device 설정
    device = args.device
    if device == 'cuda' and not torch.cuda.is_available():
        print("CUDA not available, using CPU")
        device = 'cpu'

    print(f"\n{'='*70}")
    print(f"U-Net++ Training Configuration")
    print(f"{'='*70}")
    print(f"  Training Images: {args.train_images}")
    print(f"  Training Masks: {args.train_masks}")
    print(f"  Val Images: {args.val_images}")
    print(f"  Val Masks: {args.val_masks}")
    print(f"  Image Size: {args.image_size}x{args.image_size}")
    print(f"  Batch Size: {args.batch_size}")
    print(f"  Learning Rate: {args.lr}")
    print(f"  Epochs: {args.epochs}")
    print(f"  Device: {device}")
    print(f"  Use NIR: {args.use_nir}")
    print(f"  Use Attention: {args.use_attention}")
    print(f"  Early Stopping: {args.early_stopping}")
    print(f"{'='*70}\n")

    # 데이터로더 생성
    print("Creating dataloaders...")
    train_loader, val_loader = create_dataloaders(
        train_image_dir=args.train_images,
        train_mask_dir=args.train_masks,
        val_image_dir=args.val_images,
        val_mask_dir=args.val_masks,
        batch_size=args.batch_size,
        num_workers=args.num_workers,
        image_size=(args.image_size, args.image_size)
    )

    print(f"✓ Train batches: {len(train_loader)}")
    print(f"✓ Val batches: {len(val_loader)}\n")

    # 모델 생성
    print("Creating model...")
    model = create_solar_panel_model(
        pretrained=False,
        use_nir=args.use_nir,
        device=device
    )

    # 모델 정보 출력
    from models.unet_plusplus import print_model_info
    print_model_info(model)

    # Loss function
    criterion = CombinedLoss(
        bce_weight=args.bce_weight,
        dice_weight=args.dice_weight,
        use_focal=args.use_focal
    )

    # Optimizer
    optimizer = optim.AdamW(
        model.parameters(),
        lr=args.lr,
        weight_decay=args.weight_decay
    )

    # Scheduler
    scheduler = ReduceLROnPlateau(
        optimizer,
        mode='min',
        factor=0.5,
        patience=5,
        verbose=True
    )

    # 체크포인트 디렉토리에 타임스탬프 추가
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    checkpoint_dir = os.path.join(args.checkpoint_dir, f"unet_plusplus_{timestamp}")
    log_dir = os.path.join(args.log_dir, f"unet_plusplus_{timestamp}")

    # Trainer 생성
    trainer = Trainer(
        model=model,
        train_loader=train_loader,
        val_loader=val_loader,
        criterion=criterion,
        optimizer=optimizer,
        scheduler=scheduler,
        device=device,
        checkpoint_dir=checkpoint_dir,
        log_dir=log_dir
    )

    # 체크포인트에서 재개
    start_epoch = 0
    if args.resume:
        print(f"\nResuming from checkpoint: {args.resume}")
        start_epoch = trainer.load_checkpoint(args.resume)

    # 학습 시작
    try:
        trainer.train(
            num_epochs=args.epochs,
            early_stopping_patience=args.early_stopping
        )

    except KeyboardInterrupt:
        print("\n\nTraining interrupted by user!")
        print("Saving checkpoint...")
        trainer.save_checkpoint(
            epoch=len(trainer.history['train_loss']),
            filename='interrupted.pth',
            val_loss=trainer.history['val_loss'][-1] if trainer.history['val_loss'] else 0,
            val_metrics=trainer.history['val_metrics'][-1] if trainer.history['val_metrics'] else {}
        )
        print("Checkpoint saved!")

    print(f"\n{'='*70}")
    print(f"Training completed!")
    print(f"  Checkpoints saved to: {checkpoint_dir}")
    print(f"  Logs saved to: {log_dir}")
    print(f"  Best validation loss: {trainer.best_val_loss:.4f}")
    print(f"  Best F1 score: {trainer.best_f1_score:.4f}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
