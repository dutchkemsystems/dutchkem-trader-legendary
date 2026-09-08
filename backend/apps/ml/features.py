import pandas as pd
import numpy as np
from typing import List

class FeatureExtractor:
    FEATURE_NAMES = [
        'rsi', 'macd_hist', 'bb_width', 'atr_pct', 'volume_ratio',
        'price_momentum', 'volatility_regime', 'trend_strength',
        'support_distance', 'resistance_distance'
    ]
    MIN_ROWS = 30

    @property
    def feature_names(self) -> List[str]:
        return self.FEATURE_NAMES

    def extract(self, df: pd.DataFrame) -> pd.DataFrame:
        if len(df) < self.MIN_ROWS:
            raise ValueError(f"Need minimum {self.MIN_ROWS} rows, got {len(df)}")

        features = pd.DataFrame(index=df.index)

        # 1. RSI (14-period)
        features['rsi'] = self._calc_rsi(df['close'], 14)

        # 2. MACD histogram
        features['macd_hist'] = self._calc_macd_hist(df['close'])

        # 3. Bollinger Band width
        features['bb_width'] = self._calc_bb_width(df['close'])

        # 4. ATR percentage
        features['atr_pct'] = self._calc_atr_pct(df)

        # 5. Volume ratio (current/average)
        features['volume_ratio'] = df['volume'] / df['volume'].rolling(20).mean()

        # 6. Price momentum (ROC)
        features['price_momentum'] = df['close'].pct_change(10)

        # 7. Volatility regime (high/low based on ATR percentile)
        atr = self._calc_atr(df, 14)
        atr_rank = atr.rolling(50).rank(pct=True)
        features['volatility_regime'] = (atr_rank > 0.7).astype(float)

        # 8. Trend strength (ADX-like)
        features['trend_strength'] = self._calc_trend_strength(df)

        # 9. Distance to support (%)
        features['support_distance'] = self._calc_distance_to_level(df, 'support')

        # 10. Distance to resistance (%)
        features['resistance_distance'] = self._calc_distance_to_level(df, 'resistance')

        return features.dropna()

    def _calc_rsi(self, series, period):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def _calc_macd_hist(self, series):
        ema12 = series.ewm(span=12).mean()
        ema26 = series.ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        return macd - signal

    def _calc_bb_width(self, series):
        sma = series.rolling(20).mean()
        std = series.rolling(20).std()
        upper = sma + 2 * std
        lower = sma - 2 * std
        return (upper - lower) / sma

    def _calc_atr(self, df, period):
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift()).abs()
        low_close = (df['low'] - df['close'].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(period).mean()

    def _calc_atr_pct(self, df):
        atr = self._calc_atr(df, 14)
        return atr / df['close']

    def _calc_trend_strength(self, df):
        # Simplified ADX-like measure
        plus_dm = df['high'].diff()
        minus_dm = -df['low'].diff()
        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
        atr = self._calc_atr(df, 14)
        plus_di = 100 * (plus_dm.rolling(14).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(14).mean() / atr)
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        return dx.rolling(14).mean()

    def _calc_distance_to_level(self, df, level_type):
        if level_type == 'support':
            level = df['low'].rolling(20).min()
        else:
            level = df['high'].rolling(20).max()
        return (df['close'] - level) / level
