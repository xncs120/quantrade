from nautilus_trader.core.message import Event
from nautilus_trader.indicators import MovingAverageConvergenceDivergence
from nautilus_trader.model import InstrumentId
from nautilus_trader.model import Position
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.enums import PositionSide
from nautilus_trader.model.enums import PriceType
from nautilus_trader.model.events import PositionClosed
from nautilus_trader.model.events import PositionOpened
from nautilus_trader.trading.strategy import Strategy
from nautilus_trader.trading.strategy import StrategyConfig


class MACDConfig(StrategyConfig):
    instrument_id: InstrumentId
    fast_period: int = 12
    slow_period: int = 26
    trade_size: int = 1_000_000


class MACDStrategy(Strategy):
    """A MACD-based strategy that only trades on zero-line crossovers."""

    def __init__(self, config: MACDConfig):
        super().__init__(config=config)
        # Our "trading signal"
        self.macd = MovingAverageConvergenceDivergence(
            fast_period=config.fast_period, slow_period=config.slow_period, price_type=PriceType.MID
        )

        self.trade_size = Quantity.from_int(config.trade_size)

        # Track our position and MACD state
        self.position: Position | None = None
        self.last_macd_above_zero = None  # Track if MACD was above zero on last check

    def on_start(self):
        """Subscribe to market data on strategy start."""
        self.subscribe_quote_ticks(instrument_id=self.config.instrument_id)

    def on_stop(self):
        """Clean up on strategy stop."""
        self.close_all_positions(self.config.instrument_id)
        self.unsubscribe_quote_ticks(instrument_id=self.config.instrument_id)

    def on_quote_tick(self, tick: QuoteTick):
        """Process incoming quote ticks."""
        # Update indicator
        self.macd.handle_quote_tick(tick)

        if not self.macd.initialized:
            return  # Wait for indicator to warm up

        # Check for trading opportunities
        self.check_signals()

    def on_event(self, event: Event):
        """Handle position events."""
        if isinstance(event, PositionOpened):
            self.position = self.cache.position(event.position_id)
            self._log.info(f"Position opened: {self.position.side} @ {self.position.avg_px_open}")
        elif isinstance(event, PositionClosed):
            if self.position and self.position.id == event.position_id:
                self._log.info(f"Position closed with PnL: {self.position.realized_pnl}")
                self.position = None

    def check_signals(self):
        """Check MACD signals - only act on actual crossovers."""
        current_macd = self.macd.value
        current_above_zero = current_macd > 0

        # Skip if this is the first reading
        if self.last_macd_above_zero is None:
            self.last_macd_above_zero = current_above_zero
            return

        # Only act on actual crossovers
        if self.last_macd_above_zero != current_above_zero:
            if current_above_zero:  # Just crossed above zero
                # Only go long if we're not already long
                if not self.is_long:
                    # Close any short position first
                    if self.is_short:
                        self.close_position(self.position)
                    # Then go long (but only when flat)
                    self.go_long()

            else:  # Just crossed below zero
                # Only go short if we're not already short
                if not self.is_short:
                    # Close any long position first
                    if self.is_long:
                        self.close_position(self.position)
                    # Then go short (but only when flat)
                    self.go_short()

        self.last_macd_above_zero = current_above_zero

    def go_long(self):
        """Enter long position only if flat."""
        if self.is_flat:
            order = self.order_factory.market(
                instrument_id=self.config.instrument_id,
                order_side=OrderSide.BUY,
                quantity=self.trade_size,
            )
            self.submit_order(order)
            self._log.info(f"Going LONG - MACD crossed above zero: {self.macd.value:.6f}")

    def go_short(self):
        """Enter short position only if flat."""
        if self.is_flat:
            order = self.order_factory.market(
                instrument_id=self.config.instrument_id,
                order_side=OrderSide.SELL,
                quantity=self.trade_size,
            )
            self.submit_order(order)
            self._log.info(f"Going SHORT - MACD crossed below zero: {self.macd.value:.6f}")

    @property
    def is_flat(self) -> bool:
        """Check if we have no position."""
        return self.position is None

    @property
    def is_long(self) -> bool:
        """Check if we have a long position."""
        return self.position and self.position.side == PositionSide.LONG

    @property
    def is_short(self) -> bool:
        """Check if we have a short position."""
        return self.position and self.position.side == PositionSide.SHORT

    def on_dispose(self):
        """Clean up on strategy disposal."""

from nautilus_trader.model.objects import Price


class MACDEnhancedConfig(StrategyConfig):
    instrument_id: InstrumentId
    fast_period: int = 12
    slow_period: int = 26
    trade_size: int = 1_000_000
    entry_threshold: float = 0.00005
    exit_threshold: float = 0.00002
    stop_loss_pips: int = 20  # Stop loss in pips
    take_profit_pips: int = 40  # Take profit in pips


class MACDEnhancedStrategy(Strategy):
    """Enhanced MACD strategy with stop-loss and take-profit."""

    def __init__(self, config: MACDEnhancedConfig):
        super().__init__(config=config)
        self.macd = MovingAverageConvergenceDivergence(
            fast_period=config.fast_period, slow_period=config.slow_period, price_type=PriceType.MID
        )

        self.trade_size = Quantity.from_int(config.trade_size)
        self.position: Position | None = None
        self.last_macd_sign = 0

    def on_start(self):
        """Subscribe to market data on strategy start."""
        self.subscribe_quote_ticks(instrument_id=self.config.instrument_id)

    def on_stop(self):
        """Clean up on strategy stop."""
        self.cancel_all_orders(self.config.instrument_id)
        self.close_all_positions(self.config.instrument_id)
        self.unsubscribe_quote_ticks(instrument_id=self.config.instrument_id)

    def on_quote_tick(self, tick: QuoteTick):
        """Process incoming quote ticks."""
        self.macd.handle_quote_tick(tick)

        if not self.macd.initialized:
            return

        self.check_signals(tick)

    def on_event(self, event: Event):
        """Handle position events."""
        if isinstance(event, PositionOpened):
            self.position = self.cache.position(event.position_id)
            self._log.info(f"Position opened: {self.position.side} @ {self.position.avg_px_open}")
            # Place stop-loss and take-profit orders
            self.place_exit_orders()
        elif isinstance(event, PositionClosed):
            if self.position and self.position.id == event.position_id:
                pnl = self.position.realized_pnl
                self._log.info(f"Position closed with PnL: {pnl}")
                self.position = None
                # Cancel any remaining exit orders
                self.cancel_all_orders(self.config.instrument_id)

    def check_signals(self, tick: QuoteTick):
        """Check MACD signals and manage positions."""
        current_macd = self.macd.value
        current_sign = 1 if current_macd > 0 else -1

        # Skip if we already have a position
        if self.position:
            return

        # Detect MACD zero-line crossover
        if self.last_macd_sign != 0 and self.last_macd_sign != current_sign:
            if current_sign > 0:
                self.go_long(tick)
            else:
                self.go_short(tick)

        # Entry signals based on threshold
        elif abs(current_macd) > self.config.entry_threshold:
            if current_macd > self.config.entry_threshold:
                self.go_long(tick)
            elif current_macd < -self.config.entry_threshold:
                self.go_short(tick)

        self.last_macd_sign = current_sign

    def go_long(self, tick: QuoteTick):
        """Enter long position."""
        if self.position:
            return  # Already have a position

        order = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=OrderSide.BUY,
            quantity=self.trade_size,
        )
        self.submit_order(order)
        self._log.info(f"Going LONG @ {tick.ask_price} - MACD: {self.macd.value:.6f}")

    def go_short(self, tick: QuoteTick):
        """Enter short position."""
        if self.position:
            return  # Already have a position

        order = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=OrderSide.SELL,
            quantity=self.trade_size,
        )
        self.submit_order(order)
        self._log.info(f"Going SHORT @ {tick.bid_price} - MACD: {self.macd.value:.6f}")

    def place_exit_orders(self):
        """Place stop-loss and take-profit orders for the current position."""
        if not self.position:
            return

        entry_price = float(self.position.avg_px_open)
        pip_value = 0.0001  # For FX pairs (adjust for different instruments)

        if self.position.side == PositionSide.LONG:
            # Long position: stop below entry, target above
            stop_price = entry_price - (self.config.stop_loss_pips * pip_value)
            target_price = entry_price + (self.config.take_profit_pips * pip_value)

            # Stop-loss order
            stop_loss = self.order_factory.stop_market(
                instrument_id=self.config.instrument_id,
                order_side=OrderSide.SELL,
                quantity=self.trade_size,
                trigger_price=Price.from_str(f"{stop_price:.5f}"),
            )
            self.submit_order(stop_loss)

            # Take-profit order
            take_profit = self.order_factory.limit(
                instrument_id=self.config.instrument_id,
                order_side=OrderSide.SELL,
                quantity=self.trade_size,
                price=Price.from_str(f"{target_price:.5f}"),
            )
            self.submit_order(take_profit)

            self._log.info(
                f"Placed LONG exit orders - Stop: {stop_price:.5f}, Target: {target_price:.5f}"
            )

        else:  # SHORT position
            # Short position: stop above entry, target below
            stop_price = entry_price + (self.config.stop_loss_pips * pip_value)
            target_price = entry_price - (self.config.take_profit_pips * pip_value)

            # Stop-loss order
            stop_loss = self.order_factory.stop_market(
                instrument_id=self.config.instrument_id,
                order_side=OrderSide.BUY,
                quantity=self.trade_size,
                trigger_price=Price.from_str(f"{stop_price:.5f}"),
            )
            self.submit_order(stop_loss)

            # Take-profit order
            take_profit = self.order_factory.limit(
                instrument_id=self.config.instrument_id,
                order_side=OrderSide.BUY,
                quantity=self.trade_size,
                price=Price.from_str(f"{target_price:.5f}"),
            )
            self.submit_order(take_profit)

            self._log.info(
                f"Placed SHORT exit orders - Stop: {stop_price:.5f}, Target: {target_price:.5f}"
            )

    def on_dispose(self):
        """Clean up on strategy disposal."""