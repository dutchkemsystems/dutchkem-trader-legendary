import pickle
import numpy as np
from dataclasses import dataclass
from typing import Optional
from pathlib import Path


@dataclass
class Prediction:
    probability: float
    direction: str
    model_name: str


class PredictionModel:
    def __init__(self, model_type: str = "xgboost"):
        self.model_type = model_type
        self.model = None
        self._init_model()

    def _init_model(self):
        if self.model_type == "xgboost":
            import xgboost as xgb
            self.model = xgb.XGBClassifier(
                n_estimators=100,
                max_depth=6,
                learning_rate=0.1,
                eval_metric='logloss',
            )
        elif self.model_type == "lightgbm":
            import lightgbm as lgb
            self.model = lgb.LGBMClassifier(
                n_estimators=100,
                max_depth=6,
                learning_rate=0.1,
            )
        else:
            raise ValueError(f"Unknown model type: {self.model_type}")

    def train(self, X: np.ndarray, y: np.ndarray):
        self.model.fit(X, y)

    def predict(self, X: np.ndarray) -> Prediction:
        prob = self.model.predict_proba(X)[0]
        p_up = float(prob[1])
        direction = "UP" if p_up >= 0.5 else "DOWN"
        return Prediction(probability=p_up, direction=direction, model_name=self.model_type)

    def save(self, path):
        with open(path, 'wb') as f:
            pickle.dump({'model': self.model, 'type': self.model_type}, f)

    @classmethod
    def load(cls, path):
        with open(path, 'rb') as f:
            data = pickle.load(f)
        instance = cls(model_type=data['type'])
        instance.model = data['model']
        return instance
