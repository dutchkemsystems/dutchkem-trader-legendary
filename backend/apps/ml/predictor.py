import numpy as np
from dataclasses import dataclass
from .features import FeatureExtractor
from .model import PredictionModel


@dataclass
class MLPrediction:
    p_up: float
    direction: str
    model_name: str
    features_used: int


class MLPredictor:
    def __init__(self, model_type: str = "xgboost"):
        self.extractor = FeatureExtractor()
        self.model = PredictionModel(model_type)

    def predict_from_features(self, features: np.ndarray) -> MLPrediction:
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
