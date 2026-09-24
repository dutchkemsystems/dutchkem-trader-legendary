"""Perceptron Neural Network — PyTorch-based ML model.

Inspired by GrokUltimateForexPro from MT4. Implements a simple
feedforward perceptron for price direction prediction.

Uses PyTorch (available in the environment) for neural network computation.
"""

import logging
import os
import pickle
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

log = logging.getLogger(__name__)

# Try to import PyTorch
try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    log.warning("PyTorch not available — perceptron will use numpy fallback")


@dataclass
class PerceptronPrediction:
    """Perceptron prediction result."""
    probability: float  # 0-1 (probability of UP)
    direction: str  # 'UP' or 'DOWN'
    confidence: float  # 0-1
    model_name: str = 'perceptron'


class PerceptronNet(nn.Module):
    """Simple feedforward perceptron network.
    
    Architecture (from GrokUltimateForexPro):
    - Input: 5 features (RSI, MA diff, volume ratio, S/R distance, momentum)
    - Hidden: 10 neurons, tanh activation
    - Output: 1 neuron, sigmoid activation
    """
    
    def __init__(self, input_size: int = 5, hidden_size: int = 10):
        super().__init__()
        self.layer1 = nn.Linear(input_size, hidden_size)
        self.activation = nn.Tanh()
        self.output = nn.Linear(hidden_size, 1)
        self.sigmoid = nn.Sigmoid()
    
    def forward(self, x):
        x = self.activation(self.layer1(x))
        x = self.sigmoid(self.output(x))
        return x


class DeepPerceptronNet(nn.Module):
    """Deeper perceptron (from Ultimate AI v24.004).
    
    Architecture:
    - Input: 10 features
    - Hidden layer 1: 20 neurons, tanh
    - Hidden layer 2: 20 neurons, tanh
    - Hidden layer 3: 20 neurons, tanh
    - Output: 1 neuron, sigmoid
    """
    
    def __init__(self, input_size: int = 10, hidden_size: int = 20):
        super().__init__()
        self.layer1 = nn.Linear(input_size, hidden_size)
        self.layer2 = nn.Linear(hidden_size, hidden_size)
        self.layer3 = nn.Linear(hidden_size, hidden_size)
        self.output = nn.Linear(hidden_size, 1)
        self.tanh = nn.Tanh()
        self.sigmoid = nn.Sigmoid()
    
    def forward(self, x):
        x = self.tanh(self.layer1(x))
        x = self.tanh(self.layer2(x))
        x = self.tanh(self.layer3(x))
        x = self.sigmoid(self.output(x))
        return x


class PerceptronModel:
    """Perceptron ML model for price direction prediction.
    
    Two modes:
    1. Simple (5 features): RSI, MA diff, volume ratio, S/R distance, momentum
    2. Deep (10 features): Full feature set from FeatureExtractor
    
    Usage:
        model = PerceptronModel(mode='simple')
        model.train(X_train, y_train)
        pred = model.predict(features)
    """
    
    def __init__(self, mode: str = 'simple', model_path: str = None):
        """Initialize Perceptron.
        
        Args:
            mode: 'simple' (5 features) or 'deep' (10 features)
            model_path: Path to load saved model
        """
        self.mode = mode
        self.input_size = 5 if mode == 'simple' else 10
        self.model = None
        self.trained = False
        self.scaler_mean = None
        self.scaler_std = None
        
        if TORCH_AVAILABLE:
            if mode == 'simple':
                self.model = PerceptronNet(input_size=self.input_size)
            else:
                self.model = DeepPerceptronNet(input_size=self.input_size)
        
        if model_path and os.path.exists(model_path):
            self.load(model_path)
    
    def train(
        self,
        X: np.ndarray,
        y: np.ndarray,
        epochs: int = 100,
        learning_rate: float = 0.01,
        batch_size: int = 32,
        validation_split: float = 0.2,
    ) -> dict:
        """Train the perceptron model.
        
        Args:
            X: Feature matrix (n_samples, input_size)
            y: Labels (n_samples,) — 0 or 1
            epochs: Training epochs
            learning_rate: Adam learning rate
            batch_size: Mini-batch size
            validation_split: Fraction for validation
            
        Returns:
            Training history dict
        """
        if not TORCH_AVAILABLE:
            log.warning("Perceptron: PyTorch not available, using numpy fallback")
            return self._train_numpy(X, y)
        
        # Normalize features
        self.scaler_mean = np.mean(X, axis=0)
        self.scaler_std = np.std(X, axis=0) + 1e-8
        X_norm = (X - self.scaler_mean) / self.scaler_std
        
        # Split
        n = len(X_norm)
        n_val = int(n * validation_split)
        indices = np.random.permutation(n)
        val_idx = indices[:n_val]
        train_idx = indices[n_val:]
        
        X_train = torch.FloatTensor(X_norm[train_idx])
        y_train = torch.FloatTensor(y[train_idx]).unsqueeze(1)
        X_val = torch.FloatTensor(X_norm[val_idx])
        y_val = torch.FloatTensor(y[val_idx]).unsqueeze(1)
        
        # Train
        optimizer = optim.Adam(self.model.parameters(), lr=learning_rate)
        criterion = nn.BCELoss()
        
        history = {'train_loss': [], 'val_loss': [], 'val_acc': []}
        best_val_loss = float('inf')
        
        for epoch in range(epochs):
            self.model.train()
            
            # Mini-batch training
            for i in range(0, len(X_train), batch_size):
                batch_X = X_train[i:i+batch_size]
                batch_y = y_train[i:i+batch_size]
                
                optimizer.zero_grad()
                output = self.model(batch_X)
                loss = criterion(output, batch_y)
                loss.backward()
                optimizer.step()
            
            # Validation
            self.model.eval()
            with torch.no_grad():
                val_output = self.model(X_val)
                val_loss = criterion(val_output, y_val)
                val_pred = (val_output > 0.5).float()
                val_acc = (val_pred == y_val).float().mean()
            
            history['train_loss'].append(loss.item())
            history['val_loss'].append(val_loss.item())
            history['val_acc'].append(val_acc.item())
            
            # Early stopping
            if val_loss.item() < best_val_loss:
                best_val_loss = val_loss.item()
                best_state = {k: v.clone() for k, v in self.model.state_dict().items()}
            
            if (epoch + 1) % 20 == 0:
                log.info(f"Perceptron epoch {epoch+1}/{epochs}: "
                         f"loss={loss.item():.4f} val_loss={val_loss.item():.4f} "
                         f"val_acc={val_acc.item():.3f}")
        
        # Restore best model
        self.model.load_state_dict(best_state)
        self.trained = True
        
        return history
    
    def predict(self, features: np.ndarray) -> PerceptronPrediction:
        """Predict price direction from features.
        
        Args:
            features: Feature vector (input_size,)
            
        Returns:
            PerceptronPrediction
        """
        if not self.trained:
            return PerceptronPrediction(
                probability=0.5, direction='UP',
                confidence=0.0, model_name=f'perceptron({self.mode},untrained)'
            )
        
        if TORCH_AVAILABLE:
            return self._predict_torch(features)
        else:
            return self._predict_numpy(features)
    
    def _predict_torch(self, features: np.ndarray) -> PerceptronPrediction:
        """Predict using PyTorch model."""
        # Normalize
        features_norm = (features - self.scaler_mean) / self.scaler_std
        x = torch.FloatTensor(features_norm).unsqueeze(0)
        
        self.model.eval()
        with torch.no_grad():
            prob = self.model(x).item()
        
        direction = 'UP' if prob >= 0.5 else 'DOWN'
        confidence = abs(prob - 0.5) * 2
        
        return PerceptronPrediction(
            probability=prob,
            direction=direction,
            confidence=confidence,
            model_name=f'perceptron({self.mode})',
        )
    
    def _predict_numpy(self, features: np.ndarray) -> PerceptronPrediction:
        """Predict using numpy fallback (no trained model)."""
        # Simple heuristic
        rsi = features[0] if len(features) > 0 else 0.5
        momentum = features[3] if len(features) > 3 else 0.0
        
        prob = 0.5 + momentum * 0.3
        prob = np.clip(prob, 0.0, 1.0)
        
        direction = 'UP' if prob >= 0.5 else 'DOWN'
        confidence = abs(prob - 0.5) * 2
        
        return PerceptronPrediction(
            probability=prob,
            direction=direction,
            confidence=confidence,
            model_name='perceptron(numpy_fallback)',
        )
    
    def _train_numpy(self, X: np.ndarray, y: np.ndarray) -> dict:
        """Fallback training with numpy (no PyTorch)."""
        # Simple logistic regression via gradient descent
        n_features = X.shape[1]
        self.weights = np.zeros(n_features)
        self.bias = 0.0
        self.scaler_mean = np.mean(X, axis=0)
        self.scaler_std = np.std(X, axis=0) + 1e-8
        
        X_norm = (X - self.scaler_mean) / self.scaler_std
        
        lr = 0.01
        history = {'train_loss': []}
        
        for epoch in range(100):
            # Forward
            z = X_norm @ self.weights + self.bias
            pred = 1 / (1 + np.exp(-np.clip(z, -500, 500)))
            
            # Loss
            loss = -np.mean(y * np.log(pred + 1e-8) + (1 - y) * np.log(1 - pred + 1e-8))
            history['train_loss'].append(loss)
            
            # Gradient
            error = pred - y
            self.weights -= lr * (X_norm.T @ error) / len(y)
            self.bias -= lr * np.mean(error)
        
        self.trained = True
        return history
    
    def save(self, path: str):
        """Save model to disk."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        data = {
            'mode': self.mode,
            'input_size': self.input_size,
            'scaler_mean': self.scaler_mean,
            'scaler_std': self.scaler_std,
            'trained': self.trained,
        }
        
        if TORCH_AVAILABLE and self.model is not None:
            data['model_state'] = self.model.state_dict()
        elif hasattr(self, 'weights'):
            data['weights'] = self.weights
            data['bias'] = self.bias
        
        with open(path, 'wb') as f:
            pickle.dump(data, f)
        
        log.info(f"PerceptronModel: Saved to {path}")
    
    def load(self, path: str):
        """Load model from disk."""
        with open(path, 'rb') as f:
            data = pickle.load(f)
        
        self.mode = data.get('mode', self.mode)
        self.input_size = data.get('input_size', self.input_size)
        self.scaler_mean = data.get('scaler_mean')
        self.scaler_std = data.get('scaler_std')
        self.trained = data.get('trained', False)
        
        if TORCH_AVAILABLE and 'model_state' in data:
            if self.mode == 'simple':
                self.model = PerceptronNet(input_size=self.input_size)
            else:
                self.model = DeepPerceptronNet(input_size=self.input_size)
            self.model.load_state_dict(data['model_state'])
        elif 'weights' in data:
            self.weights = data['weights']
            self.bias = data.get('bias', 0.0)
        
        log.info(f"PerceptronModel: Loaded from {path}")
