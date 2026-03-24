"""
Signal scoring module for the Polymarket BTC UpDown 5m trading bot.

This module provides a SignalScorer class to evaluate trading signals based on
various indicators and determine the optimal trading direction.
"""

from dataclasses import dataclass

from src.config import CONFIG


@dataclass(slots=True)
class SignalResult:
    """Dataclass representing the result of a signal scoring.

    Attributes:
        direction: Direction of the signal ("UP", "DOWN", or "SKIP").
        confidence: Confidence level of the signal (0.0 to 1.0).
        suggested_side: Suggested side for trading ("Up", "Down", or None).
    """

    direction: str
    confidence: float
    suggested_side: str | None


class SignalScorer:
    """Class to score trading signals based on various indicators."""

    def score(
        self,
        delta: float,
        volatility: float,
        gbm_prob: float,
        rsi: float,
        ema_spread: float,
        time_remaining: float,
    ) -> SignalResult:
        """Score a trading signal based on various indicators.

        Args:
            delta: Delta as a percentage.
            volatility: Volatility of BTC.
            gbm_prob: Probability from the GBM model.
            rsi: Relative Strength Index.
            ema_spread: EMA spread.
            time_remaining: Time remaining in the current 5-minute window.

        Returns:
            SignalResult containing the direction, confidence, and suggested side.
        """
        # Determine direction based on GBM probability and edge buffer
        if gbm_prob > 0.5 + CONFIG.EDGE_BUFFER:
            direction = "UP"
            suggested_side = "Up"
        elif gbm_prob < 0.5 - CONFIG.EDGE_BUFFER:
            direction = "DOWN"
            suggested_side = "Down"
        else:
            direction = "SKIP"
            suggested_side = None

        # Calculate confidence
        confidence = self._calculate_confidence(delta, volatility, gbm_prob, rsi, ema_spread)

        return SignalResult(direction=direction, confidence=confidence, suggested_side=suggested_side)

    def _calculate_confidence(
        self, delta: float, volatility: float, gbm_prob: float, rsi: float, ema_spread: float
    ) -> float:
        """Calculate the confidence level of the signal.

        Args:
            delta: Delta as a percentage.
            volatility: Volatility of BTC.
            gbm_prob: Probability from the GBM model.
            rsi: Relative Strength Index.
            ema_spread: EMA spread.

        Returns:
            Confidence level as a float between 0.0 and 1.0.
        """
        # Calculate individual confidence components
        gbm_confidence = abs(gbm_prob - 0.5) * 2.0
        delta_confidence = min(abs(delta) / 0.01, 1.0)  # Cap at 1%
        rsi_confidence = 0.0
        if rsi > 70:
            rsi_confidence = (rsi - 70) / 30.0
        elif rsi < 30:
            rsi_confidence = (30 - rsi) / 30.0
        volatility_confidence = 1.0 - min(volatility / 0.1, 1.0)  # Cap at 10%

        # Combine confidence components with weights
        confidence = (
            gbm_confidence * 0.6
            + delta_confidence * 0.2
            + rsi_confidence * 0.1
            + volatility_confidence * 0.1
        )

        return confidence
