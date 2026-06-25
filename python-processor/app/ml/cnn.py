from __future__ import annotations


def build_small_cnn(num_classes: int):
    """Build the optional training model without making PyTorch a core dependency."""
    if num_classes < 2:
        raise ValueError("num_classes must be at least 2")
    try:
        import torch.nn as nn
    except ImportError as exc:
        raise RuntimeError(
            "PyTorch is required only in the optional ML training environment"
        ) from exc

    class SmallRfCnn(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.features = nn.Sequential(
                nn.Conv2d(1, 32, kernel_size=3, padding=1),
                nn.BatchNorm2d(32),
                nn.ReLU(inplace=True),
                nn.MaxPool2d(2),
                nn.Conv2d(32, 64, kernel_size=3, padding=1),
                nn.BatchNorm2d(64),
                nn.ReLU(inplace=True),
                nn.MaxPool2d(2),
                nn.Conv2d(64, 128, kernel_size=3, padding=1),
                nn.BatchNorm2d(128),
                nn.ReLU(inplace=True),
                nn.AdaptiveAvgPool2d((1, 1)),
            )
            self.classifier = nn.Linear(128, num_classes)

        def forward(self, inputs):
            features = self.features(inputs)
            return self.classifier(features.flatten(1))

    return SmallRfCnn()
