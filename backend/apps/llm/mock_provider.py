import random
import json
from .models import LLMResponse


class MockProvider:
    def analyze(self, prompt, output_schema=None):
        signals = ["BUY", "SELL", "HOLD"]
        signal = random.choice(signals)
        confidence = round(random.uniform(0.5, 0.95), 2)

        text = (
            f"Mock Analysis: Based on the prompt provided, I recommend {signal} "
            f"with {confidence * 100:.0f}% confidence. The market shows mixed signals "
            f"with some bullish momentum but also resistance levels nearby."
        )

        parsed = {}
        if output_schema:
            if "signal" in str(output_schema):
                parsed["signal"] = signal
            if "confidence" in str(output_schema):
                parsed["confidence"] = confidence

        return LLMResponse(
            text=text,
            confidence=confidence,
            parsed=parsed,
            model_used="mock",
            tokens_used=0,
        )
