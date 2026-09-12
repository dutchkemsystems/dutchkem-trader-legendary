"""ML Data Loader — fetches real historical data and prepares it for ML training."""

import asyncio
import logging
from typing import Optional, List, Tuple

import numpy as np
import pandas as pd

from data.manager import MarketDataManager
from data.models import Timeframe
from data.providers import StubProvider
from data.registry import ProviderRegistry
from apps.ml.features import FeatureExtractor

logger = logging.getLogger(__name__)

# Map string timeframe to Timeframe enum
TIMEFRAME_MAP = {
    "1M": Timeframe.ONE_MINUTE,
    "5M": Timeframe.FIVE_MINUTES,
    "15M": Timeframe.FIFTEEN_MINUTES,
    "1H": Timeframe.ONE_HOUR,
    "4H": Timeframe.FOUR_HOURS,
    "1D": Timeframe.ONE_DAY,
    # Legacy aliases
    "Daily": Timeframe.ONE_DAY,
    "hourly": Timeframe.ONE_HOUR,
}


class MLDataLoader:
    """Loads real historical data via MarketDataManager for ML training."""

    def __init__(self, data_manager: Optional[MarketDataManager] = None):
        if data_manager is None:
            # Use default registry which chains: AKShare (free) -> StubProvider (fallback)
            # This ensures real market data is used when available
            data_manager = MarketDataManager()
        self.data_manager = data_manager
        self.extractor = FeatureExtractor()

    async def fetch_candles(
        self, symbol: str, timeframe: str = "1H", limit: int = 500
    ) -> pd.DataFrame:
        """Fetch candles from MarketDataManager and return as DataFrame."""
        tf = TIMEFRAME_MAP.get(timeframe, Timeframe.ONE_HOUR)
        candles = await self.data_manager.get_candles(symbol, tf, limit=limit)

        if not candles:
            raise ValueError(f"No candles returned for {symbol} {timeframe}")

        df = pd.DataFrame([c.to_dict() for c in candles])
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp")
        df = df.sort_index()

        # Normalize column names to lowercase
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        return df

    def load_training_data(
        self,
        symbol: str,
        timeframe: str = "1H",
        limit: int = 500,
        forecast_period: int = 1,
    ) -> Tuple[pd.DataFrame, pd.Series]:
        """Load and prepare training data with features and labels.

        Returns:
            X: Feature matrix (N x 10)
            y: Binary labels (1 = price went up, 0 = price went down)
        """
        # Fetch candles synchronously via run_until_complete fallback
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Already in an event loop — use a new thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    df = pool.submit(
                        asyncio.run,
                        self.fetch_candles(symbol, timeframe, limit),
                    ).result()
            else:
                df = loop.run_until_complete(
                    self.fetch_candles(symbol, timeframe, limit)
                )
        except RuntimeError:
            df = asyncio.run(self.fetch_candles(symbol, timeframe, limit))

        # Need extra rows for label generation (future return)
        min_candles = max(self.extractor.MIN_ROWS + forecast_period, 50)
        if len(df) < min_candles:
            raise ValueError(
                f"Need at least {min_candles} candles for training, got {len(df)}"
            )

        # Generate labels: 1 if price went up after forecast_period candles, else 0
        future_return = df["close"].shift(-forecast_period) - df["close"]
        labels = (future_return > 0).astype(int)

        # Extract features
        features = self.extractor.extract(df)

        # Align labels with features (features may have dropped NaN rows)
        common_idx = features.index.intersection(labels.index)
        X = features.loc[common_idx]
        y = labels.loc[common_idx]

        # Drop any remaining NaN rows
        mask = X.notna().all(axis=1) & y.notna()
        X = X[mask]
        y = y[mask]

        return X, y

    def load_training_data_from_df(
        self, df: pd.DataFrame, forecast_period: int = 1
    ) -> Tuple[pd.DataFrame, pd.Series]:
        """Prepare training data from an existing DataFrame (no network call).

        Useful for testing or when data is already loaded.
        """
        if len(df) < self.extractor.MIN_ROWS + forecast_period:
            raise ValueError(
                f"Need at least {self.extractor.MIN_ROWS + forecast_period} rows, got {len(df)}"
            )

        future_return = df["close"].shift(-forecast_period) - df["close"]
        labels = (future_return > 0).astype(int)

        features = self.extractor.extract(df)

        common_idx = features.index.intersection(labels.index)
        X = features.loc[common_idx]
        y = labels.loc[common_idx]

        mask = X.notna().all(axis=1) & y.notna()
        X = X[mask]
        y = y[mask]

        return X, y
