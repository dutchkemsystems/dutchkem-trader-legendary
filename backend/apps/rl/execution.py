"""
Feature 9: Reinforcement Learning for Optimal Execution
Uses DQN to choose order type, timing, and splitting.
"""
import numpy as np
from typing import Dict, Tuple
from collections import deque
import random


class DQNAgent:
    """Deep Q-Network agent for execution optimization."""

    def __init__(self, state_size: int = 6, action_size: int = 5):
        self.state_size = state_size
        self.action_size = action_size
        self.memory = deque(maxlen=1000)
        self.gamma = 0.95  # Discount factor
        self.epsilon = 1.0  # Exploration rate
        self.epsilon_min = 0.01
        self.epsilon_decay = 0.995
        self.learning_rate = 0.001
        self.model = None
        self.target_model = None

    def _build_model(self):
        """Build neural network model."""
        try:
            from tensorflow.keras.models import Sequential
            from tensorflow.keras.layers import Dense
            from tensorflow.keras.optimizers import Adam

            model = Sequential([
                Dense(24, input_dim=self.state_size, activation="relu"),
                Dense(24, activation="relu"),
                Dense(self.action_size, activation="linear"),
            ])
            model.compile(loss="mse", optimizer=Adam(learning_rate=self.learning_rate))
            return model
        except ImportError:
            return None

    def get_state(self, spread: float, volatility: float, time_of_day: float,
                  order_book_imbalance: float, position_size: float, urgency: float) -> np.ndarray:
        """Convert market conditions to state vector."""
        return np.array([
            spread,
            volatility,
            time_of_day / 24.0,
            order_book_imbalance,
            position_size,
            urgency,
        ]).reshape(1, -1)

    def act(self, state: np.ndarray) -> int:
        """Choose action using epsilon-greedy policy."""
        if self.model is None:
            # Fallback: random action
            return random.randrange(self.action_size)

        if np.random.rand() <= self.epsilon:
            return random.randrange(self.action_size)

        q_values = self.model.predict(state, verbose=0)
        return np.argmax(q_values[0])

    def decode_action(self, action: int) -> Dict:
        """Decode action index to execution parameters."""
        actions = {
            0: {"type": "market", "split": 1, "offset": 0},
            1: {"type": "limit", "split": 1, "offset": 0.0001},
            2: {"type": "limit", "split": 1, "offset": 0.0002},
            3: {"type": "market", "split": 2, "offset": 0},
            4: {"type": "market", "split": 3, "offset": 0},
        }
        return actions.get(action, actions[0])

    def remember(self, state, action, reward, next_state, done):
        """Store experience in memory."""
        self.memory.append((state, action, reward, next_state, done))

    def replay(self, batch_size: int = 32):
        """Train on batch of experiences."""
        if self.model is None or len(self.memory) < batch_size:
            return

        batch = random.sample(self.memory, batch_size)
        states = np.array([e[0] for e in batch]).reshape(-1, self.state_size)
        next_states = np.array([e[3] for e in batch]).reshape(-1, self.state_size)

        q_values = self.model.predict(states, verbose=0)
        q_next = self.target_model.predict(next_states, verbose=0)

        for i, (state, action, reward, next_state, done) in enumerate(batch):
            if done:
                q_values[i][action] = reward
            else:
                q_values[i][action] = reward + self.gamma * np.amax(q_next[i])

        self.model.fit(states, q_values, epochs=1, verbose=0)

        # Decay epsilon
        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay

    def calculate_reward(self, slippage: float, fill_rate: float) -> float:
        """Calculate reward for execution quality."""
        # Negative slippage is bad, high fill rate is good
        reward = -slippage * 10 + fill_rate * 5
        return reward


class ExecutionOptimizer:
    """Optimize trade execution using RL."""

    def __init__(self):
        self.agent = DQNAgent()
        self.execution_history = []

    def get_execution_plan(self, market_data: Dict) -> Dict:
        """Get optimal execution plan for a trade."""
        state = self.agent.get_state(
            spread=market_data.get("spread", 0),
            volatility=market_data.get("volatility", 0),
            time_of_day=market_data.get("time_of_day", 12),
            order_book_imbalance=market_data.get("imbalance", 0),
            position_size=market_data.get("size", 0.01),
            urgency=market_data.get("urgency", 0.5),
        )

        action = self.agent.act(state)
        plan = self.agent.decode_action(action)

        return {
            **plan,
            "action_index": action,
            "confidence": 1.0 - self.agent.epsilon,
        }

    def record_execution(self, plan: Dict, actual_slippage: float, fill_rate: float):
        """Record execution result for learning."""
        reward = self.agent.calculate_reward(actual_slippage, fill_rate)
        self.execution_history.append({
            "plan": plan,
            "slippage": actual_slippage,
            "fill_rate": fill_rate,
            "reward": reward,
        })

    def get_metrics(self) -> Dict:
        """Get execution quality metrics."""
        if not self.execution_history:
            return {"avg_slippage": 0, "avg_fill_rate": 0, "total_trades": 0}

        slippages = [h["slippage"] for h in self.execution_history]
        fill_rates = [h["fill_rate"] for h in self.execution_history]

        return {
            "avg_slippage": np.mean(slippages),
            "avg_fill_rate": np.mean(fill_rates),
            "total_trades": len(self.execution_history),
            "epsilon": self.agent.epsilon,
        }
