"""Models module"""
from .solar_detector import SimpleSolarDetector, MockSolarDetector

# U-Net++ advanced detector (PyTorch 필요)
try:
    from .advanced_solar_detector import AdvancedSolarDetector, SolarDetector
    __all__ = ['SimpleSolarDetector', 'MockSolarDetector', 'AdvancedSolarDetector', 'SolarDetector']
except ImportError:
    __all__ = ['SimpleSolarDetector', 'MockSolarDetector']
