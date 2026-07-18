"""U-Net++ 학습 Trainer"""
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from torch.optim import Optimizer
from torch.optim.lr_scheduler import _LRScheduler
import os
from pathlib import Path
from tqdm import tqdm
import json
from datetime import datetime
from typing import Dict, Optional
import numpy as np


class Trainer:
    """U-Net++ 학습 Trainer"""

    def __init__(
        self,
        model: nn.Module,
        train_loader: DataLoader,
        val_loader: DataLoader,
        criterion: nn.Module,
        optimizer: Optimizer,
        scheduler: Optional[_LRScheduler] = None,
        device: str = 'cuda',
        checkpoint_dir: str = 'checkpoints',
        log_dir: str = 'logs'
    ):
        self.model = model.to(device)
        self.train_loader = train_loader
        self.val_loader = val_loader
        self.criterion = criterion
        self.optimizer = optimizer
        self.scheduler = scheduler
        self.device = device

        # 디렉토리 생성
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # 학습 기록
        self.history = {
            'train_loss': [],
            'val_loss': [],
            'val_metrics': []
        }

        self.best_val_loss = float('inf')
        self.best_f1_score = 0.0

    def train_epoch(self, epoch: int) -> float:
        """한 에포크 학습"""
        self.model.train()
        total_loss = 0.0
        total_bce_loss = 0.0
        total_dice_loss = 0.0

        pbar = tqdm(self.train_loader, desc=f'Epoch {epoch} [Train]')

        for batch_idx, batch in enumerate(pbar):
            images = batch['image'].to(self.device)
            masks = batch['mask'].to(self.device)

            # Forward
            self.optimizer.zero_grad()
            outputs = self.model(images)

            # Loss 계산
            loss_dict = self.criterion(outputs, masks)
            loss = loss_dict['loss']

            # Backward
            loss.backward()
            self.optimizer.step()

            # 기록
            total_loss += loss.item()
            total_bce_loss += loss_dict.get('bce_loss', 0)
            total_dice_loss += loss_dict.get('dice_loss', 0)

            # Progress bar 업데이트
            pbar.set_postfix({
                'loss': f"{loss.item():.4f}",
                'bce': f"{loss_dict.get('bce_loss', 0):.4f}",
                'dice': f"{loss_dict.get('dice_loss', 0):.4f}"
            })

        # 평균 loss
        avg_loss = total_loss / len(self.train_loader)
        avg_bce = total_bce_loss / len(self.train_loader)
        avg_dice = total_dice_loss / len(self.train_loader)

        return avg_loss, avg_bce, avg_dice

    @torch.no_grad()
    def validate_epoch(self, epoch: int) -> tuple:
        """검증"""
        self.model.eval()
        total_loss = 0.0

        # 메트릭 누적
        all_precisions = []
        all_recalls = []
        all_f1_scores = []
        all_ious = []
        all_dices = []

        pbar = tqdm(self.val_loader, desc=f'Epoch {epoch} [Val]')

        for batch in pbar:
            images = batch['image'].to(self.device)
            masks = batch['mask'].to(self.device)

            # Forward
            outputs = self.model(images)

            # Loss
            loss_dict = self.criterion(outputs, masks)
            total_loss += loss_dict['loss'].item()

            # Metrics 계산
            from .losses import calculate_metrics
            pred_sigmoid = torch.sigmoid(outputs)
            metrics = calculate_metrics(pred_sigmoid, masks, threshold=0.5)

            all_precisions.append(metrics['precision'])
            all_recalls.append(metrics['recall'])
            all_f1_scores.append(metrics['f1_score'])
            all_ious.append(metrics['iou'])
            all_dices.append(metrics['dice'])

            pbar.set_postfix({
                'loss': f"{loss_dict['loss'].item():.4f}",
                'f1': f"{metrics['f1_score']:.4f}"
            })

        # 평균
        avg_loss = total_loss / len(self.val_loader)
        avg_metrics = {
            'precision': np.mean(all_precisions),
            'recall': np.mean(all_recalls),
            'f1_score': np.mean(all_f1_scores),
            'iou': np.mean(all_ious),
            'dice': np.mean(all_dices)
        }

        return avg_loss, avg_metrics

    def train(self, num_epochs: int, early_stopping_patience: int = 10):
        """전체 학습 루프"""
        print(f"\n{'='*60}")
        print(f"Starting Training")
        print(f"  Device: {self.device}")
        print(f"  Epochs: {num_epochs}")
        print(f"  Train batches: {len(self.train_loader)}")
        print(f"  Val batches: {len(self.val_loader)}")
        print(f"{'='*60}\n")

        patience_counter = 0

        for epoch in range(1, num_epochs + 1):
            # 학습
            train_loss, train_bce, train_dice = self.train_epoch(epoch)

            # 검증
            val_loss, val_metrics = self.validate_epoch(epoch)

            # Scheduler 업데이트
            if self.scheduler is not None:
                if isinstance(self.scheduler, torch.optim.lr_scheduler.ReduceLROnPlateau):
                    self.scheduler.step(val_loss)
                else:
                    self.scheduler.step()

            # 현재 learning rate
            current_lr = self.optimizer.param_groups[0]['lr']

            # 기록
            self.history['train_loss'].append(train_loss)
            self.history['val_loss'].append(val_loss)
            self.history['val_metrics'].append(val_metrics)

            # 결과 출력
            print(f"\n{'='*60}")
            print(f"Epoch {epoch}/{num_epochs}")
            print(f"  Train Loss: {train_loss:.4f} (BCE: {train_bce:.4f}, Dice: {train_dice:.4f})")
            print(f"  Val Loss: {val_loss:.4f}")
            print(f"  Val Metrics:")
            for key, value in val_metrics.items():
                print(f"    {key}: {value:.4f}")
            print(f"  Learning Rate: {current_lr:.6f}")
            print(f"{'='*60}\n")

            # 체크포인트 저장
            is_best_loss = val_loss < self.best_val_loss
            is_best_f1 = val_metrics['f1_score'] > self.best_f1_score

            if is_best_loss:
                self.best_val_loss = val_loss
                patience_counter = 0
                self.save_checkpoint(epoch, 'best_loss.pth', val_loss, val_metrics)
                print(f"✓ Best validation loss! Saved checkpoint.")

            if is_best_f1:
                self.best_f1_score = val_metrics['f1_score']
                self.save_checkpoint(epoch, 'best_f1.pth', val_loss, val_metrics)
                print(f"✓ Best F1 score! Saved checkpoint.")

            if not is_best_loss:
                patience_counter += 1

            # 마지막 체크포인트 저장
            if epoch % 5 == 0:
                self.save_checkpoint(epoch, f'checkpoint_epoch_{epoch}.pth', val_loss, val_metrics)

            # Early stopping
            if patience_counter >= early_stopping_patience:
                print(f"\nEarly stopping triggered after {epoch} epochs")
                break

        # 학습 히스토리 저장
        self.save_history()

        print(f"\n{'='*60}")
        print(f"Training Completed!")
        print(f"  Best Val Loss: {self.best_val_loss:.4f}")
        print(f"  Best F1 Score: {self.best_f1_score:.4f}")
        print(f"{'='*60}\n")

    def save_checkpoint(self, epoch: int, filename: str, val_loss: float, val_metrics: Dict):
        """체크포인트 저장"""
        checkpoint = {
            'epoch': epoch,
            'model_state_dict': self.model.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'val_loss': val_loss,
            'val_metrics': val_metrics,
            'best_val_loss': self.best_val_loss,
            'best_f1_score': self.best_f1_score
        }

        if self.scheduler is not None:
            checkpoint['scheduler_state_dict'] = self.scheduler.state_dict()

        checkpoint_path = self.checkpoint_dir / filename
        torch.save(checkpoint, checkpoint_path)

    def load_checkpoint(self, checkpoint_path: str):
        """체크포인트 로드"""
        checkpoint = torch.load(checkpoint_path, map_location=self.device)

        self.model.load_state_dict(checkpoint['model_state_dict'])
        self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])

        if self.scheduler is not None and 'scheduler_state_dict' in checkpoint:
            self.scheduler.load_state_dict(checkpoint['scheduler_state_dict'])

        self.best_val_loss = checkpoint['best_val_loss']
        self.best_f1_score = checkpoint['best_f1_score']

        print(f"Loaded checkpoint from {checkpoint_path}")
        print(f"  Epoch: {checkpoint['epoch']}")
        print(f"  Val Loss: {checkpoint['val_loss']:.4f}")
        print(f"  F1 Score: {checkpoint['val_metrics']['f1_score']:.4f}")

        return checkpoint['epoch']

    def save_history(self):
        """학습 히스토리 저장"""
        history_path = self.log_dir / 'training_history.json'

        with open(history_path, 'w') as f:
            json.dump(self.history, f, indent=2)

        print(f"Training history saved to {history_path}")


if __name__ == "__main__":
    print("Trainer module ready!")
