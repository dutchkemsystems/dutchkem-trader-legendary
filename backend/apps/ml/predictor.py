import numpy as np
import os
from pathlib import Path
from dataclasses import dataclass
from .features import FeatureExtractor
from .model import PredictionModel

# Models directory (relative to backend/)
MODELS_DIR = Path(__file__).parent.parent.parent / "models"


@dataclass
class MLPrediction:
    p_up: float
    direction: str
    model_name: str
    features_used: int


class MLPredictor:
    def __init__(self, model_type: str = "xgboost", model_path: str = None):
        self.extractor = FeatureExtractor()
        
        # Try to load trained model from disk
        if model_path is None:
            model_path = self._find_trained_model(model_type)
        
        if model_path and os.path.exists(model_path):
            self.model = PredictionModel.load(model_path)
        else:
            self.model = PredictionModel(model_type)
    
    def _find_trained_model(self, model_type: str) -> str:
        """Find trained model file in models directory."""
        if MODELS_DIR.exists():
            model_file = MODELS_DIR / f"{model_type}_model.pkl"
            if model_file.exists():
                return str(model_file)
        return None

    def predict_from_features(self, features) -> MLPrediction:
        # Accept list, numpy array, or any array-like
        features = np.array(features, dtype=float)
        if features.ndim == 1:
            features = features.reshape(1, -1)
        pred = self.model.predict(features)
        return MLPrediction(
            p_up=pred.probability,
            direction=pred.direction,
            model_name=pred.model_name,
            features_used=features.shape[1],
        )

    @property
    def is_trained(self) -> bool:
        return self.model.trained

    def train(self, X: np.ndarray, y: np.ndarray):
        self.model.train(X, y)
