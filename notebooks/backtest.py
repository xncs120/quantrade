from nautilus_trader.backtest.node import BacktestDataConfig
from nautilus_trader.backtest.node import BacktestEngineConfig
from nautilus_trader.backtest.node import BacktestNode
from nautilus_trader.backtest.node import BacktestRunConfig
from nautilus_trader.backtest.node import BacktestVenueConfig
from nautilus_trader.config import ImportableStrategyConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.model import Quantity
from nautilus_trader.model import QuoteTick
from nautilus_trader.persistence.catalog import ParquetDataCatalog

# Load the catalog from current working directory
catalog_path = Path.cwd() / "catalog"

catalog = ParquetDataCatalog(str(catalog_path))
instruments = catalog.instruments()

print(f"Loaded catalog from: {catalog_path}")
print(f"Available instruments: {[str(i.id) for i in instruments]}")

if instruments:
    print(f"\nUsing instrument: {instruments[0].id}")
else:
    print("\nNo instruments found. Please run the data download cell first.")

engine = BacktestEngineConfig(
    strategies=[
        ImportableStrategyConfig(
            strategy_path="__main__:MACDStrategy",
            config_path="__main__:MACDConfig",
            config={
                "instrument_id": instruments[0].id,
                "fast_period": 12,
                "slow_period": 26,
            },
        )
    ],
    logging=LoggingConfig(log_level="ERROR"),
)

data = BacktestDataConfig(
    catalog_path=str(catalog.path),
    data_cls=QuoteTick,
    instrument_id=instruments[0].id,
    end_time="2020-01-10",
)

venue = BacktestVenueConfig(
    name="SIM",
    oms_type="NETTING",
    account_type="MARGIN",
    base_currency="USD",
    starting_balances=["1_000_000 USD"],
)

instruments = catalog.instruments()
instruments

config = BacktestRunConfig(
    engine=engine,
    venues=[venue],
    data=[data],
)

from nautilus_trader.backtest.results import BacktestResult


node = BacktestNode(configs=[config])

# Runs one or many configs synchronously
results: list[BacktestResult] = node.run()

