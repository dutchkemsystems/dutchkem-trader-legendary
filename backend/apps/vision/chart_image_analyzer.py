"""OpenCV-based chart image analyzer for detecting patterns from chart screenshots."""
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

import cv2
import numpy as np


@dataclass
class TrendLine:
    slope: float
    intercept: float
    start_point: Tuple[int, int]
    end_point: Tuple[int, int]
    strength: float


@dataclass
class ImageAnalysis:
    trend_lines: List[TrendLine]
    support_levels: List[float]
    resistance_levels: List[float]
    edge_density: float
    pattern_regions: List[Dict]
    reasoning: str


class ChartImageAnalyzer:
    def __init__(self):
        self._min_line_length = 50
        self._max_line_gap = 10
        self._canny_low = 50
        self._canny_high = 150

    def analyze_chart_image(self, image_path: str) -> ImageAnalysis:
        img = cv2.imread(image_path)
        if img is None:
            return ImageAnalysis(
                trend_lines=[], support_levels=[], resistance_levels=[],
                edge_density=0.0, pattern_regions=[],
                reasoning="Failed to load chart image",
            )

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, self._canny_low, self._canny_high)

        trend_lines = self._detect_trend_lines(edges, img.shape)
        horizontal_lines = self._detect_horizontal_lines(edges)
        support, resistance = self._classify_sr_lines(horizontal_lines, img.shape)
        edge_density = self._calculate_edge_density(edges)
        regions = self._detect_pattern_regions(edges, img.shape)

        reasoning = (
            f"Detected {len(trend_lines)} trend lines, "
            f"{len(support)} support, {len(resistance)} resistance levels. "
            f"Edge density: {edge_density:.3f}"
        )

        return ImageAnalysis(
            trend_lines=trend_lines,
            support_levels=support,
            resistance_levels=resistance,
            edge_density=edge_density,
            pattern_regions=regions,
            reasoning=reasoning,
        )

    def _detect_trend_lines(self, edges: np.ndarray, shape: Tuple) -> List[TrendLine]:
        lines = cv2.HoughLinesP(
            edges, 1, np.pi / 180, threshold=50,
            minLineLength=self._min_line_length,
            maxLineGap=self._max_line_gap,
        )
        if lines is None:
            return []

        trend_lines = []
        for line in lines:
            coords = line.flatten()
            x1, y1, x2, y2 = coords[:4]
            dx = x2 - x1
            dy = y2 - y1
            if abs(dx) < 5:
                continue
            slope = dy / dx
            intercept = y1 - slope * x1
            length = np.sqrt(dx**2 + dy**2)
            strength = min(1.0, length / max(shape[0], shape[1]))
            trend_lines.append(TrendLine(
                slope=slope, intercept=intercept,
                start_point=(x1, y1), end_point=(x2, y2),
                strength=strength,
            ))
        return trend_lines[:10]

    def _detect_horizontal_lines(self, edges: np.ndarray) -> List[Tuple[int, int]]:
        lines = cv2.HoughLinesP(
            edges, 1, np.pi / 180, threshold=80,
            minLineLength=100,
            maxLineGap=self._max_line_gap,
        )
        if lines is None:
            return []

        horizontal = []
        for line in lines:
            coords = line.flatten()
            x1, y1, x2, y2 = coords[:4]
            angle = abs(np.arctan2(y2 - y1, x2 - x1))
            if angle < 0.1:
                horizontal.append((min(y1, y2), max(y1, y2)))
        return horizontal

    def _classify_sr_lines(
        self, horizontal_lines: List[Tuple[int, int]], shape: Tuple
    ) -> Tuple[List[float], List[float]]:
        if not horizontal_lines:
            return [], []
        mid_y = shape[0] / 2
        support = [l[0] / shape[0] for l in horizontal_lines if l[0] > mid_y]
        resistance = [l[0] / shape[0] for l in horizontal_lines if l[0] <= mid_y]
        support.sort(reverse=True)
        resistance.sort()
        return support[:5], resistance[:5]

    def _calculate_edge_density(self, edges: np.ndarray) -> float:
        total_pixels = edges.shape[0] * edges.shape[1]
        if total_pixels == 0:
            return 0.0
        return float(np.count_nonzero(edges)) / total_pixels

    def _detect_pattern_regions(
        self, edges: np.ndarray, shape: Tuple
    ) -> List[Dict]:
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        regions = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 500:
                continue
            x, y, w, h = cv2.boundingRect(cnt)
            aspect = w / max(h, 1)
            if 0.5 < aspect < 3.0:
                regions.append({
                    'x': x, 'y': y, 'width': w, 'height': h,
                    'area': float(area), 'aspect_ratio': aspect,
                })
        regions.sort(key=lambda r: r['area'], reverse=True)
        return regions[:10]

    def preprocess_image(self, image_path: str, output_path: str) -> bool:
        img = cv2.imread(image_path)
        if img is None:
            return False
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(blurred)
        return cv2.imwrite(output_path, enhanced)
