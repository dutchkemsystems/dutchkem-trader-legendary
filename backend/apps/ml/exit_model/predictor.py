"""
Feature 6: Self-Learning Exit Optimization
Uses ML to predict optimal exit points for each trade.
"""
import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple
from pathlib import Path
import json
import logging

log = logging.getLogger("exit_model")


class ExitOptimizer:
    """Predict optimal exit price using ML."""

    def __init__(self, model_dir: str = None):
        self.model_dir = Path(model_dir) if model_dir else Path("models")
        self.model_dir.mkdir(exist_ok=True)
        self.model = None
        self.feature_names = [
            "volatility", "momentum", "time_in_trade", "unrealized_pnl",
            "atr", "rsi", "bb_position", "session_hour",
        ]

    def extract_features(self, trade_data: Dict) -> np.ndarray:
        """Extract features for exit prediction."""
        features = [
            trade_data.get("volatility", 0),
            trade_data.get("momentum", 0),
            trade_data.get("time_in_trade", 0),
            trade_data.get("unrealized_pnl", 0),
            trade_data.get("atr", 0),
            trade_data.get("rsi", 50),
            trade_data.get("bb_position", 0.5),
            trade_data.get("session_hour", 12),
        ]
        return np.array(features).reshape(1, -1)

    def predict_optimal_exit(self, trade_data: Dict) -> Dict:
        """Predict optimal exit price and confidence."""
        if self.model is None:
            # Fallback to rule-based
            return self._rule_based_exit(trade_data)

        try:
            features = self.extract_features(trade_data)
            prediction = self.model.predict(features)[0]
            confidence = self.model.predict_proba(features).max() if hasattr(self.model, "predict_proba") else 0.5

            return {
                "exit_price": prediction,
                "confidence": confidence,
                "method": "ml_model",
            }
        except Exception as e:
            log.warning(f"ML prediction failed: {e}")
            return self._rule_based_exit(trade_data)

    def _rule_based_exit(self, trade_data: Dict) -> Dict:
        """Rule-based exit prediction (fallback)."""
        entry = trade_data.get("entry_price", 0)
        current = trade_data.get("current_price", 0)
        atr = trade_data.get("atr", 0)
        direction = trade_data.get("direction", "BUY")

        if entry == 0:
            return {"exit_price": current, "confidence": 0, "method": "fallback"}

        # Simple ATR-based exit
        if direction == "BUY":
            exit_price = current + atr * 2  # Trail by 2x ATR
        else:
            exit_price = current - atr * 2

        return {
            "exit_price": exit_price,
            "confidence": 0.3,
            "method": "rule_based_atr",
        }

    def train(self, historical_trades: pd.DataFrame):
        """Train exit prediction model on historical trades."""
        try:
            from xgboost import XGBRegressor
            from sklearn.model_selection import train_test_split
            from sklearn.metrics import mean_squared_error

            if len(historical_trades) < 50:
                log.warning("Insufficient data for exit model training")
                return False

            # Prepare features and target
            X = historical_trades[self.feature_names].fillna(0)
            y = historical_trades["optimal_exit_price"].fillna(0)

            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)

            # Train model
            self.model = XGBRegressor(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.1,
                random_state=42,
            )
            self.model.fit(X_train, y_train)

            # Evaluate
            predictions = self.model.predict(X_test)
            rmse = np.sqrt(mean_squared_error(y_test, predictions))
            log.info(f"Exit model trained — RMSE: {rmse:.5f}")

            # Save model
            model_path = self.model_dir / "exit_optimizer.json"
            self.model.save_model(str(model_path))

            return True

        except ImportError:
            log.warning("XGBoost not available for exit model")
            return False

    def load_model(self) -> bool:
        """Load trained model from disk."""
        model_path = self.model_dir / "exit_optimizer.json"
        if model_path.exists():
            try:
                from xgboost import XGBRegressor
                self.model = XGBRegressor()
                self.model.load_model(str(model_path))
                log.info("Exit optimizer model loaded")
                return True
            except Exception as e:
                log.warning(f"Failed to load exit model: {e}")
        return False
