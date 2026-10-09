"""
Image Enhancement module for pre-OCR processing.
Uses OpenCV to apply deskewing, noise reduction, and binarization.
"""

import logging
import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

class ImageEnhancer:
    @staticmethod
    def enhance_for_ocr(pil_image: Image.Image) -> Image.Image:
        """
        Takes a PIL Image, applies OpenCV enhancements (grayscale, binarization, deskew),
        and returns the enhanced PIL Image.
        """
        try:
            # Convert PIL to cv2 format (numpy array)
            open_cv_image = np.array(pil_image)
            # Handle RGB to BGR conversion if needed
            if len(open_cv_image.shape) == 3 and open_cv_image.shape[2] == 3:
                open_cv_image = open_cv_image[:, :, ::-1].copy()

            # Convert to grayscale
            gray = cv2.cvtColor(open_cv_image, cv2.COLOR_BGR2GRAY) if len(open_cv_image.shape) == 3 else open_cv_image

            # Noise removal (Gaussian blur)
            blur = cv2.GaussianBlur(gray, (5, 5), 0)

            # Adaptive thresholding for binarization
            binary = cv2.adaptiveThreshold(
                blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
            )

            # Simple Deskew (find min area rectangle of coordinates)
            coords = np.column_stack(np.where(binary > 0))
            if len(coords) > 0:
                angle = cv2.minAreaRect(coords)[-1]
                if angle < -45:
                    angle = -(90 + angle)
                else:
                    angle = -angle
                
                # Rotate if the angle is significant
                if abs(angle) > 0.5:
                    (h, w) = binary.shape[:2]
                    center = (w // 2, h // 2)
                    M = cv2.getRotationMatrix2D(center, angle, 1.0)
                    binary = cv2.warpAffine(binary, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

            # Convert back to PIL
            return Image.fromarray(binary)
        except Exception as e:
            logger.warning("Image enhancement failed, returning original image: %s", e)
            return pil_image
