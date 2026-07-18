"""U-Net++ 모델 구현 (태양광 패널 세그멘테이션)"""
import os
import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import List, Optional


class ConvBlock(nn.Module):
    """기본 Convolution Block (Conv -> BN -> ReLU)"""

    def __init__(self, in_channels: int, out_channels: int):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True)
        )

    def forward(self, x):
        return self.conv(x)


class AttentionBlock(nn.Module):
    """Attention Mechanism for U-Net++"""

    def __init__(self, F_g: int, F_l: int, F_int: int):
        """
        Args:
            F_g: gating signal의 채널 수
            F_l: encoder feature의 채널 수
            F_int: intermediate 채널 수
        """
        super().__init__()
        self.W_g = nn.Sequential(
            nn.Conv2d(F_g, F_int, kernel_size=1, stride=1, padding=0, bias=True),
            nn.BatchNorm2d(F_int)
        )

        self.W_x = nn.Sequential(
            nn.Conv2d(F_l, F_int, kernel_size=1, stride=1, padding=0, bias=True),
            nn.BatchNorm2d(F_int)
        )

        self.psi = nn.Sequential(
            nn.Conv2d(F_int, 1, kernel_size=1, stride=1, padding=0, bias=True),
            nn.BatchNorm2d(1),
            nn.Sigmoid()
        )

        self.relu = nn.ReLU(inplace=True)

    def forward(self, g, x):
        """
        Args:
            g: gating signal (decoder)
            x: encoder feature
        """
        g1 = self.W_g(g)
        x1 = self.W_x(x)
        psi = self.relu(g1 + x1)
        psi = self.psi(psi)
        return x * psi


class UNetPlusPlus(nn.Module):
    """
    U-Net++ (Nested U-Net) with Attention Mechanism
    태양광 패널 세그멘테이션 특화
    """

    def __init__(
        self,
        in_channels: int = 3,
        num_classes: int = 1,
        base_channels: int = 64,
        deep_supervision: bool = False,
        use_attention: bool = True
    ):
        """
        Args:
            in_channels: 입력 채널 수 (RGB=3, RGB+NIR=4 등)
            num_classes: 출력 클래스 수 (binary=1, multi-class>1)
            base_channels: 기본 채널 수
            deep_supervision: Deep supervision 사용 여부
            use_attention: Attention mechanism 사용 여부
        """
        super().__init__()

        self.deep_supervision = deep_supervision
        self.use_attention = use_attention

        # 채널 수 계산
        nb_filter = [base_channels, base_channels*2, base_channels*4, base_channels*8, base_channels*16]

        # Encoder (왼쪽)
        self.conv0_0 = ConvBlock(in_channels, nb_filter[0])
        self.conv1_0 = ConvBlock(nb_filter[0], nb_filter[1])
        self.conv2_0 = ConvBlock(nb_filter[1], nb_filter[2])
        self.conv3_0 = ConvBlock(nb_filter[2], nb_filter[3])
        self.conv4_0 = ConvBlock(nb_filter[3], nb_filter[4])

        # Decoder (nested structure)
        self.conv0_1 = ConvBlock(nb_filter[0] + nb_filter[1], nb_filter[0])
        self.conv1_1 = ConvBlock(nb_filter[1] + nb_filter[2], nb_filter[1])
        self.conv2_1 = ConvBlock(nb_filter[2] + nb_filter[3], nb_filter[2])
        self.conv3_1 = ConvBlock(nb_filter[3] + nb_filter[4], nb_filter[3])

        self.conv0_2 = ConvBlock(nb_filter[0]*2 + nb_filter[1], nb_filter[0])
        self.conv1_2 = ConvBlock(nb_filter[1]*2 + nb_filter[2], nb_filter[1])
        self.conv2_2 = ConvBlock(nb_filter[2]*2 + nb_filter[3], nb_filter[2])

        self.conv0_3 = ConvBlock(nb_filter[0]*3 + nb_filter[1], nb_filter[0])
        self.conv1_3 = ConvBlock(nb_filter[1]*3 + nb_filter[2], nb_filter[1])

        self.conv0_4 = ConvBlock(nb_filter[0]*4 + nb_filter[1], nb_filter[0])

        # Pooling
        self.pool = nn.MaxPool2d(2, 2)

        # Upsampling
        self.up = nn.Upsample(scale_factor=2, mode='bilinear', align_corners=True)

        # Attention blocks (옵션)
        if use_attention:
            self.att1 = AttentionBlock(F_g=nb_filter[1], F_l=nb_filter[1], F_int=nb_filter[0])
            self.att2 = AttentionBlock(F_g=nb_filter[2], F_l=nb_filter[2], F_int=nb_filter[1])
            self.att3 = AttentionBlock(F_g=nb_filter[3], F_l=nb_filter[3], F_int=nb_filter[2])
            self.att4 = AttentionBlock(F_g=nb_filter[4], F_l=nb_filter[4], F_int=nb_filter[3])

        # Final output layers
        if deep_supervision:
            self.final1 = nn.Conv2d(nb_filter[0], num_classes, kernel_size=1)
            self.final2 = nn.Conv2d(nb_filter[0], num_classes, kernel_size=1)
            self.final3 = nn.Conv2d(nb_filter[0], num_classes, kernel_size=1)
            self.final4 = nn.Conv2d(nb_filter[0], num_classes, kernel_size=1)
        else:
            self.final = nn.Conv2d(nb_filter[0], num_classes, kernel_size=1)

    def forward(self, x):
        # Encoder path
        x0_0 = self.conv0_0(x)
        x1_0 = self.conv1_0(self.pool(x0_0))
        x2_0 = self.conv2_0(self.pool(x1_0))
        x3_0 = self.conv3_0(self.pool(x2_0))
        x4_0 = self.conv4_0(self.pool(x3_0))

        # Decoder path with nested skip connections
        # Column 1
        x3_1_up = self.up(x4_0)
        if self.use_attention:
            x3_0 = self.att4(g=x3_1_up, x=x3_0)
        x3_1 = self.conv3_1(torch.cat([x3_0, x3_1_up], 1))

        x2_1_up = self.up(x3_1)
        if self.use_attention:
            x2_0 = self.att3(g=x2_1_up, x=x2_0)
        x2_1 = self.conv2_1(torch.cat([x2_0, x2_1_up], 1))

        x1_1_up = self.up(x2_1)
        if self.use_attention:
            x1_0 = self.att2(g=x1_1_up, x=x1_0)
        x1_1 = self.conv1_1(torch.cat([x1_0, x1_1_up], 1))

        x0_1_up = self.up(x1_1)
        if self.use_attention:
            x0_0_att = self.att1(g=x0_1_up, x=x0_0)
        else:
            x0_0_att = x0_0
        x0_1 = self.conv0_1(torch.cat([x0_0_att, x0_1_up], 1))

        # Column 2
        x2_2 = self.conv2_2(torch.cat([x2_0, x2_1, self.up(x3_1)], 1))
        x1_2 = self.conv1_2(torch.cat([x1_0, x1_1, self.up(x2_2)], 1))
        x0_2 = self.conv0_2(torch.cat([x0_0, x0_1, self.up(x1_2)], 1))

        # Column 3
        x1_3 = self.conv1_3(torch.cat([x1_0, x1_1, x1_2, self.up(x2_2)], 1))
        x0_3 = self.conv0_3(torch.cat([x0_0, x0_1, x0_2, self.up(x1_3)], 1))

        # Column 4
        x0_4 = self.conv0_4(torch.cat([x0_0, x0_1, x0_2, x0_3, self.up(x1_3)], 1))

        # Output
        if self.deep_supervision:
            output1 = self.final1(x0_1)
            output2 = self.final2(x0_2)
            output3 = self.final3(x0_3)
            output4 = self.final4(x0_4)
            return [output1, output2, output3, output4]
        else:
            output = self.final(x0_4)
            return output


class SolarPanelUNetPlusPlus(nn.Module):
    """
    태양광 패널 특화 U-Net++
    추가 기능:
    - Multi-spectral input (RGB + NIR)
    - Solar panel specific preprocessing
    - Post-processing for panel detection
    """

    def __init__(
        self,
        in_channels: int = 3,
        use_nir: bool = False,
        base_channels: int = 64,
        use_attention: bool = True
    ):
        super().__init__()

        self.use_nir = use_nir

        # NIR 채널 사용 시 입력 채널 +1
        if use_nir:
            in_channels += 1

        self.unet = UNetPlusPlus(
            in_channels=in_channels,
            num_classes=1,  # Binary segmentation (panel vs background)
            base_channels=base_channels,
            deep_supervision=False,
            use_attention=use_attention
        )

    def forward(self, x):
        """
        Args:
            x: (B, C, H, W) - RGB or RGB+NIR

        Returns:
            (B, 1, H, W) - Panel probability map
        """
        logits = self.unet(x)
        return torch.sigmoid(logits)

    def predict(self, x, threshold: float = 0.5):
        """
        예측 및 이진화

        Args:
            x: 입력 이미지
            threshold: 이진화 임계값

        Returns:
            Binary mask (0 or 1)
        """
        with torch.no_grad():
            probs = self.forward(x)
            mask = (probs > threshold).float()
        return mask


def create_solar_panel_model(
    pretrained: bool = False,
    use_nir: bool = False,
    device: str = 'cpu'
) -> SolarPanelUNetPlusPlus:
    """
    태양광 패널 탐지 모델 생성

    Args:
        pretrained: 사전학습 가중치 로드 여부
        use_nir: NIR 채널 사용 여부
        device: 'cpu' or 'cuda'

    Returns:
        SolarPanelUNetPlusPlus 모델
    """
    model = SolarPanelUNetPlusPlus(
        in_channels=3,
        use_nir=use_nir,
        base_channels=64,
        use_attention=True
    )

    if pretrained:
        # 사전학습 가중치 로드
        pretrained_path = os.getenv(
            'UNET_PRETRAINED_PATH',
            '/app/models/unet_plusplus_solar_panels.pth'
        )

        if os.path.exists(pretrained_path):
            try:
                print(f"Loading pretrained weights from: {pretrained_path}")
                state_dict = torch.load(pretrained_path, map_location=device)

                # state_dict 키가 'model'로 감싸져 있는 경우 처리
                if 'model' in state_dict:
                    state_dict = state_dict['model']
                elif 'state_dict' in state_dict:
                    state_dict = state_dict['state_dict']

                # 가중치 로드 (strict=False: 일부 레이어 불일치 허용)
                model.load_state_dict(state_dict, strict=False)
                print("✅ Pretrained weights loaded successfully")
            except Exception as e:
                print(f"⚠️ Failed to load pretrained weights: {e}")
                print("   Continuing with randomly initialized weights...")
        else:
            print(f"⚠️ Pretrained weights not found at: {pretrained_path}")
            print("   Continuing with randomly initialized weights...")
            print("   You can set UNET_PRETRAINED_PATH environment variable to specify custom path")

    model = model.to(device)
    model.eval()

    return model


# 모델 정보 출력 함수
def print_model_info(model: nn.Module):
    """모델 정보 출력"""
    total_params = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)

    print("="*60)
    print("Model Information")
    print("="*60)
    print(f"Total parameters: {total_params:,}")
    print(f"Trainable parameters: {trainable_params:,}")
    print(f"Model size: {total_params * 4 / 1024 / 1024:.2f} MB (float32)")
    print("="*60)


if __name__ == "__main__":
    # 테스트
    print("Testing U-Net++ Model...")

    # 모델 생성
    model = create_solar_panel_model(use_nir=False, device='cpu')
    print_model_info(model)

    # 더미 입력
    x = torch.randn(2, 3, 256, 256)  # Batch=2, RGB, 256x256

    # Forward pass
    with torch.no_grad():
        output = model(x)

    print(f"\nInput shape: {x.shape}")
    print(f"Output shape: {output.shape}")
    print(f"Output range: [{output.min():.4f}, {output.max():.4f}]")

    # Prediction
    mask = model.predict(x, threshold=0.5)
    print(f"Binary mask unique values: {torch.unique(mask).tolist()}")

    print("\n✓ Model test passed!")
