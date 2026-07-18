"""세그멘테이션 Loss Functions"""
import torch
import torch.nn as nn
import torch.nn.functional as F


class DiceLoss(nn.Module):
    """
    Dice Loss for segmentation
    Dice Coefficient = 2 * |A ∩ B| / (|A| + |B|)
    Dice Loss = 1 - Dice Coefficient
    """

    def __init__(self, smooth: float = 1e-6):
        super().__init__()
        self.smooth = smooth

    def forward(self, pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        """
        Args:
            pred: (B, 1, H, W) - 예측 (sigmoid 적용 후)
            target: (B, 1, H, W) - 실제 마스크 (0 or 1)

        Returns:
            Dice loss (scalar)
        """
        pred = pred.contiguous().view(-1)
        target = target.contiguous().view(-1)

        intersection = (pred * target).sum()
        dice = (2. * intersection + self.smooth) / (pred.sum() + target.sum() + self.smooth)

        return 1 - dice


class IoULoss(nn.Module):
    """
    IoU (Intersection over Union) Loss
    IoU = |A ∩ B| / |A ∪ B|
    """

    def __init__(self, smooth: float = 1e-6):
        super().__init__()
        self.smooth = smooth

    def forward(self, pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        pred = pred.contiguous().view(-1)
        target = target.contiguous().view(-1)

        intersection = (pred * target).sum()
        union = pred.sum() + target.sum() - intersection

        iou = (intersection + self.smooth) / (union + self.smooth)

        return 1 - iou


class FocalLoss(nn.Module):
    """
    Focal Loss
    FL(p_t) = -α_t * (1 - p_t)^γ * log(p_t)

    불균형 데이터셋에 효과적
    """

    def __init__(self, alpha: float = 0.25, gamma: float = 2.0):
        super().__init__()
        self.alpha = alpha
        self.gamma = gamma

    def forward(self, pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        """
        Args:
            pred: (B, 1, H, W) - logits (sigmoid 전)
            target: (B, 1, H, W) - 실제 마스크

        Returns:
            Focal loss
        """
        bce_loss = F.binary_cross_entropy_with_logits(pred, target, reduction='none')

        # p_t 계산
        pred_prob = torch.sigmoid(pred)
        p_t = target * pred_prob + (1 - target) * (1 - pred_prob)

        # α_t 계산
        alpha_t = target * self.alpha + (1 - target) * (1 - self.alpha)

        # Focal loss
        focal_weight = alpha_t * (1 - p_t) ** self.gamma
        focal_loss = focal_weight * bce_loss

        return focal_loss.mean()


class CombinedLoss(nn.Module):
    """
    결합 Loss: BCE + Dice Loss

    세그멘테이션에서 가장 효과적인 조합
    """

    def __init__(
        self,
        bce_weight: float = 0.5,
        dice_weight: float = 0.5,
        use_focal: bool = False
    ):
        super().__init__()
        self.bce_weight = bce_weight
        self.dice_weight = dice_weight

        if use_focal:
            self.bce = FocalLoss()
        else:
            self.bce = nn.BCEWithLogitsLoss()

        self.dice = DiceLoss()

    def forward(self, pred: torch.Tensor, target: torch.Tensor) -> dict:
        """
        Args:
            pred: (B, 1, H, W) - logits (sigmoid 전)
            target: (B, 1, H, W) - 실제 마스크

        Returns:
            loss dictionary
        """
        # BCE Loss (logits 사용)
        bce_loss = self.bce(pred, target)

        # Dice Loss (sigmoid 적용 후)
        pred_sigmoid = torch.sigmoid(pred)
        dice_loss = self.dice(pred_sigmoid, target)

        # 결합
        total_loss = self.bce_weight * bce_loss + self.dice_weight * dice_loss

        return {
            'loss': total_loss,
            'bce_loss': bce_loss.item(),
            'dice_loss': dice_loss.item()
        }


class TverskyLoss(nn.Module):
    """
    Tversky Loss
    False Positive와 False Negative의 가중치를 조절 가능

    α > β: False Negative에 더 많은 페널티 (Recall 중시)
    α < β: False Positive에 더 많은 페널티 (Precision 중시)
    """

    def __init__(self, alpha: float = 0.7, beta: float = 0.3, smooth: float = 1e-6):
        super().__init__()
        self.alpha = alpha
        self.beta = beta
        self.smooth = smooth

    def forward(self, pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        pred = pred.contiguous().view(-1)
        target = target.contiguous().view(-1)

        true_pos = (pred * target).sum()
        false_neg = ((1 - pred) * target).sum()
        false_pos = (pred * (1 - target)).sum()

        tversky = (true_pos + self.smooth) / (
            true_pos + self.alpha * false_neg + self.beta * false_pos + self.smooth
        )

        return 1 - tversky


def calculate_metrics(pred: torch.Tensor, target: torch.Tensor, threshold: float = 0.5) -> dict:
    """
    세그멘테이션 메트릭 계산

    Args:
        pred: (B, 1, H, W) - 예측 확률 (0-1)
        target: (B, 1, H, W) - 실제 마스크 (0 or 1)
        threshold: 이진화 임계값

    Returns:
        metrics dictionary
    """
    # 이진화
    pred_binary = (pred > threshold).float()

    # Flatten
    pred_flat = pred_binary.contiguous().view(-1)
    target_flat = target.contiguous().view(-1)

    # True Positive, False Positive, False Negative, True Negative
    tp = ((pred_flat == 1) & (target_flat == 1)).sum().float()
    fp = ((pred_flat == 1) & (target_flat == 0)).sum().float()
    fn = ((pred_flat == 0) & (target_flat == 1)).sum().float()
    tn = ((pred_flat == 0) & (target_flat == 0)).sum().float()

    # Precision, Recall, F1
    precision = tp / (tp + fp + 1e-6)
    recall = tp / (tp + fn + 1e-6)
    f1_score = 2 * precision * recall / (precision + recall + 1e-6)

    # Accuracy
    accuracy = (tp + tn) / (tp + fp + fn + tn + 1e-6)

    # IoU (Intersection over Union)
    intersection = (pred_flat * target_flat).sum()
    union = pred_flat.sum() + target_flat.sum() - intersection
    iou = (intersection + 1e-6) / (union + 1e-6)

    # Dice Coefficient
    dice = (2 * intersection + 1e-6) / (pred_flat.sum() + target_flat.sum() + 1e-6)

    return {
        'precision': precision.item(),
        'recall': recall.item(),
        'f1_score': f1_score.item(),
        'accuracy': accuracy.item(),
        'iou': iou.item(),
        'dice': dice.item()
    }


if __name__ == "__main__":
    # 테스트
    print("Testing Loss Functions...")

    # 더미 데이터
    batch_size = 4
    pred = torch.randn(batch_size, 1, 256, 256)  # logits
    target = torch.randint(0, 2, (batch_size, 1, 256, 256)).float()

    # Combined Loss 테스트
    criterion = CombinedLoss(bce_weight=0.5, dice_weight=0.5)
    loss_dict = criterion(pred, target)

    print(f"Total Loss: {loss_dict['loss']:.4f}")
    print(f"BCE Loss: {loss_dict['bce_loss']:.4f}")
    print(f"Dice Loss: {loss_dict['dice_loss']:.4f}")

    # Metrics 테스트
    pred_sigmoid = torch.sigmoid(pred)
    metrics = calculate_metrics(pred_sigmoid, target, threshold=0.5)

    print("\nMetrics:")
    for key, value in metrics.items():
        print(f"  {key}: {value:.4f}")

    print("\n✓ Loss functions test passed!")
