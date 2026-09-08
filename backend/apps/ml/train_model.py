#!/usr/bin/env python
"""Train ML model on real historical data.

Usage:
    cd backend
    python -m apps.ml.train_model --symbol EURUSD --timeframe 1H --limit 500
    python -m apps.ml.train_model --symbol AAPL --timeframe 1D --limit 200
"""

import argparse
import asyncio
import logging
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from apps.ml.data_loader import MLDataLoader
from apps.ml.model import PredictionModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def train(
    symbol: str = "EURUSD",
    timeframe: str = "1H",
    limit: int = 500,
    model_type: str = "xgboost",
    save_path: str = "models",
):
    """Train ML model on real data."""
    logger.info("=" * 60)
    logger.info("ML MODEL TRAINING — Real Historical Data")
    logger.info("=" * 60)
    logger.info(f"Symbol:     {symbol}")
    logger.info(f"Timeframe:  {timeframe}")
    logger.info(f"Candles:    {limit}")
    logger.info(f"Model:      {model_type}")
    logger.info("=" * 60)

    # Load data
    loader = MLDataLoader()
    logger.info("Fetching candles from data provider...")
    X, y = loader.load_training_data(symbol, timeframe, limit)

    logger.info(f"Training data: {X.shape[0]} samples, {X.shape[1]} features")
    logger.info(f"Label distribution: BUY={y.sum()}, SELL={len(y) - y.sum()}")

    # Train model
    model = PredictionModel(model_type=model_type)
    logger.info("Training model...")
    model.train(X, y)
    logger.info("Training complete!")

    # Save model
    os.makedirs(save_path, exist_ok=True)
    model_path = model.save(save_path)
    logger.info(f"Model saved to: {model_path}")

    # Quick sanity check — predict on last sample
    pred = model.predict(X.iloc[[-1]].values)
    logger.info(f"Sanity check — last sample: P(UP)={pred.probability:.4f}, direction={pred.direction}")

    logger.info("=" * 60)
    logger.info("DONE")
    logger.info("=" * 60)

    return model_path


def main():
    parser = argparse.ArgumentParser(description="Train ML model on real data")
    parser.add_argument("--symbol", default="EURUSD", help="Trading symbol")
    parser.add_argument("--timeframe", default="1H", help="Timeframe (1M, 5M, 15M, 1H, 4H, 1D)")
    parser.add_argument("--limit", type=int, default=500, help="Number of candles to fetch")
    parser.add_argument("--model", default="xgboost", choices=["xgboost", "lightgbm"], help="Model type")
    parser.add_argument("--save-path", default="models", help="Directory to save model")
    args = parser.parse_args()

    asyncio.run(train(args.symbol, args.timeframe, args.limit, args.model, args.save_path))


if __name__ == "__main__":
    main()
