"""태양광 패널 세그멘테이션 데이터셋"""
import os
import numpy as np
import torch
from torch.utils.data import Dataset
from PIL import Image
import albumentations as A
from albumentations.pytorch import ToTensorV2
from typing import Optional, Tuple, List
import json


class SolarPanelDataset(Dataset):
    """
    태양광 패널 세그멘테이션 데이터셋

    디렉토리 구조:
    data/
    ├── images/
    │   ├── img001.jpg
    │   ├── img002.jpg
    │   └── ...
    └── masks/
        ├── img001.png
        ├── img002.png
        └── ...
    """

    def __init__(
        self,
        image_dir: str,
        mask_dir: str,
        transform: Optional[A.Compose] = None,
        image_size: Tuple[int, int] = (256, 256)
    ):
        """
        Args:
            image_dir: 이미지 디렉토리 경로
            mask_dir: 마스크 디렉토리 경로
            transform: Albumentations transform
            image_size: 이미지 크기 (H, W)
        """
        self.image_dir = image_dir
        self.mask_dir = mask_dir
        self.image_size = image_size

        # 이미지 파일 목록
        self.images = sorted([
            f for f in os.listdir(image_dir)
            if f.endswith(('.jpg', '.jpeg', '.png', '.tif', '.tiff'))
        ])

        # Transform
        if transform is None:
            self.transform = self.get_default_transform()
        else:
            self.transform = transform

        print(f"Loaded {len(self.images)} images from {image_dir}")

    def __len__(self):
        return len(self.images)

    def __getitem__(self, idx):
        # 이미지 로드
        img_name = self.images[idx]
        img_path = os.path.join(self.image_dir, img_name)

        image = np.array(Image.open(img_path).convert('RGB'))

        # 마스크 로드 (확장자 변경 가능)
        mask_name = os.path.splitext(img_name)[0] + '.png'
        mask_path = os.path.join(self.mask_dir, mask_name)

        if not os.path.exists(mask_path):
            # 다른 확장자 시도
            mask_name = os.path.splitext(img_name)[0] + '.jpg'
            mask_path = os.path.join(self.mask_dir, mask_name)

        if os.path.exists(mask_path):
            mask = np.array(Image.open(mask_path).convert('L'))
            # 이진화 (0 or 1)
            mask = (mask > 127).astype(np.float32)
        else:
            # 마스크 없으면 빈 마스크
            mask = np.zeros((image.shape[0], image.shape[1]), dtype=np.float32)

        # Transform 적용
        if self.transform:
            transformed = self.transform(image=image, mask=mask)
            image = transformed['image']
            mask = transformed['mask']

        # Mask shape: (H, W) -> (1, H, W)
        if len(mask.shape) == 2:
            mask = mask.unsqueeze(0)

        return {
            'image': image,
            'mask': mask,
            'filename': img_name
        }

    def get_default_transform(self):
        """기본 Transform (훈련용)"""
        return A.Compose([
            A.Resize(self.image_size[0], self.image_size[1]),
            A.HorizontalFlip(p=0.5),
            A.VerticalFlip(p=0.5),
            A.RandomRotate90(p=0.5),
            A.ShiftScaleRotate(
                shift_limit=0.1,
                scale_limit=0.1,
                rotate_limit=15,
                p=0.5
            ),
            A.RandomBrightnessContrast(
                brightness_limit=0.2,
                contrast_limit=0.2,
                p=0.5
            ),
            A.GaussNoise(p=0.3),
            A.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225]
            ),
            ToTensorV2()
        ])

    @staticmethod
    def get_validation_transform(image_size: Tuple[int, int] = (256, 256)):
        """검증용 Transform (증강 없음)"""
        return A.Compose([
            A.Resize(image_size[0], image_size[1]),
            A.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225]
            ),
            ToTensorV2()
        ])


class COCOSolarPanelDataset(Dataset):
    """
    COCO 형식의 태양광 패널 데이터셋

    디렉토리 구조:
    data/
    ├── images/
    │   └── *.jpg
    ├── annotations/
    │   ├── train.json
    │   └── val.json
    """

    def __init__(
        self,
        image_dir: str,
        annotation_file: str,
        transform: Optional[A.Compose] = None,
        image_size: Tuple[int, int] = (256, 256)
    ):
        self.image_dir = image_dir
        self.image_size = image_size
        self.transform = transform or self.get_default_transform()

        # COCO annotations 로드
        with open(annotation_file, 'r') as f:
            self.coco_data = json.load(f)

        # 이미지 ID -> 파일명 매핑
        self.images = {img['id']: img for img in self.coco_data['images']}

        # 이미지 ID -> annotations 매핑
        self.img_to_anns = {}
        for ann in self.coco_data['annotations']:
            img_id = ann['image_id']
            if img_id not in self.img_to_anns:
                self.img_to_anns[img_id] = []
            self.img_to_anns[img_id].append(ann)

        self.image_ids = list(self.images.keys())

        print(f"Loaded {len(self.image_ids)} images from COCO dataset")

    def __len__(self):
        return len(self.image_ids)

    def __getitem__(self, idx):
        img_id = self.image_ids[idx]
        img_info = self.images[img_id]

        # 이미지 로드
        img_path = os.path.join(self.image_dir, img_info['file_name'])
        image = np.array(Image.open(img_path).convert('RGB'))

        # 마스크 생성
        mask = np.zeros((img_info['height'], img_info['width']), dtype=np.uint8)

        if img_id in self.img_to_anns:
            for ann in self.img_to_anns[img_id]:
                # Segmentation polygon -> mask
                if 'segmentation' in ann:
                    from pycocotools import mask as coco_mask
                    rle = coco_mask.frPyObjects(
                        ann['segmentation'],
                        img_info['height'],
                        img_info['width']
                    )
                    m = coco_mask.decode(rle)
                    if len(m.shape) == 3:
                        m = m.max(axis=2)
                    mask = np.maximum(mask, m)

        mask = mask.astype(np.float32)

        # Transform
        if self.transform:
            transformed = self.transform(image=image, mask=mask)
            image = transformed['image']
            mask = transformed['mask']

        if len(mask.shape) == 2:
            mask = mask.unsqueeze(0)

        return {
            'image': image,
            'mask': mask,
            'filename': img_info['file_name']
        }

    def get_default_transform(self):
        return SolarPanelDataset.get_default_transform(None, self.image_size)


def create_dataloaders(
    train_image_dir: str,
    train_mask_dir: str,
    val_image_dir: str,
    val_mask_dir: str,
    batch_size: int = 8,
    num_workers: int = 4,
    image_size: Tuple[int, int] = (256, 256)
):
    """
    Train/Val 데이터로더 생성

    Args:
        train_image_dir: 훈련 이미지 디렉토리
        train_mask_dir: 훈련 마스크 디렉토리
        val_image_dir: 검증 이미지 디렉토리
        val_mask_dir: 검증 마스크 디렉토리
        batch_size: 배치 크기
        num_workers: 워커 수
        image_size: 이미지 크기

    Returns:
        train_loader, val_loader
    """
    # 훈련 데이터셋
    train_dataset = SolarPanelDataset(
        image_dir=train_image_dir,
        mask_dir=train_mask_dir,
        transform=None,  # 기본 transform 사용
        image_size=image_size
    )

    # 검증 데이터셋
    val_dataset = SolarPanelDataset(
        image_dir=val_image_dir,
        mask_dir=val_mask_dir,
        transform=SolarPanelDataset.get_validation_transform(image_size),
        image_size=image_size
    )

    # 데이터로더
    train_loader = torch.utils.data.DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=num_workers,
        pin_memory=True,
        drop_last=True
    )

    val_loader = torch.utils.data.DataLoader(
        val_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=True
    )

    return train_loader, val_loader


if __name__ == "__main__":
    # 테스트
    print("Testing SolarPanelDataset...")

    # Mock 데이터 생성
    import tempfile
    import shutil

    temp_dir = tempfile.mkdtemp()
    img_dir = os.path.join(temp_dir, "images")
    mask_dir = os.path.join(temp_dir, "masks")

    os.makedirs(img_dir)
    os.makedirs(mask_dir)

    # 더미 이미지 생성
    for i in range(5):
        img = Image.fromarray(np.random.randint(0, 255, (512, 512, 3), dtype=np.uint8))
        img.save(os.path.join(img_dir, f"img{i:03d}.jpg"))

        mask = Image.fromarray(np.random.randint(0, 2, (512, 512), dtype=np.uint8) * 255)
        mask.save(os.path.join(mask_dir, f"img{i:03d}.png"))

    # 데이터셋 생성
    dataset = SolarPanelDataset(img_dir, mask_dir, image_size=(256, 256))

    print(f"Dataset size: {len(dataset)}")

    # 샘플 로드
    sample = dataset[0]
    print(f"Image shape: {sample['image'].shape}")
    print(f"Mask shape: {sample['mask'].shape}")
    print(f"Filename: {sample['filename']}")

    # 정리
    shutil.rmtree(temp_dir)

    print("\n✓ Dataset test passed!")
