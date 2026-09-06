import uuid
from django.db import models
from django.contrib.auth.models import User


class UserProxy(User):
    class Meta:
        proxy = True
        db_table = "users"


class AnalystResult(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="analyst_results")
    ticker = models.CharField(max_length=20)
    analyst_type = models.CharField(max_length=50)
    signal = models.CharField(max_length=20)
    confidence = models.FloatField()
    reasoning = models.TextField(blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        db_table = "analyst_results"

    def __str__(self):
        return f"{self.analyst_type} - {self.ticker}: {self.signal} ({self.confidence:.0%})"


class ConsensusResult(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="consensus_results")
    ticker = models.CharField(max_length=20)
    consensus_signal = models.CharField(max_length=20)
    weight = models.FloatField()
    analyst_results = models.ManyToManyField(AnalystResult, related_name="consensus_groups")
    reasoning = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        db_table = "consensus_results"

    def __str__(self):
        return f"Consensus {self.ticker}: {self.consensus_signal} (w={self.weight:.2f})"


class Trade(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SUBMITTED = "SUBMITTED", "Submitted"
        PARTIAL = "PARTIAL", "Partial"
        EXECUTED = "EXECUTED", "Executed"
        CANCELLED = "CANCELLED", "Cancelled"
        FAILED = "FAILED", "Failed"

    class Side(models.TextChoices):
        BUY = "BUY", "Buy"
        SELL = "SELL", "Sell"

    class OrderType(models.TextChoices):
        MARKET = "MARKET", "Market"
        LIMIT = "LIMIT", "Limit"
        STOP = "STOP", "Stop"
        STOP_LIMIT = "STOP_LIMIT", "Stop Limit"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="trades")
    ticker = models.CharField(max_length=20)
    side = models.CharField(max_length=4, choices=Side.choices)
    order_type = models.CharField(max_length=10, choices=OrderType.choices, default=OrderType.MARKET)
    quantity = models.DecimalField(max_digits=15, decimal_places=6)
    price = models.DecimalField(max_digits=15, decimal_places=6)
    stop_loss = models.DecimalField(max_digits=15, decimal_places=6, null=True, blank=True)
    take_profit = models.DecimalField(max_digits=15, decimal_places=6, null=True, blank=True)
    trailing_stop = models.DecimalField(max_digits=15, decimal_places=6, null=True, blank=True)
    broker_order_id = models.CharField(max_length=50, null=True, blank=True)
    filled_quantity = models.DecimalField(max_digits=15, decimal_places=6, default=0)
    fill_price = models.DecimalField(max_digits=15, decimal_places=6, null=True, blank=True)
    commission = models.DecimalField(max_digits=15, decimal_places=6, default=0)
    slippage = models.DecimalField(max_digits=15, decimal_places=6, default=0)
    pnl = models.DecimalField(max_digits=15, decimal_places=6, default=0)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    consensus = models.ForeignKey(ConsensusResult, on_delete=models.SET_NULL, null=True, blank=True)
    executed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        db_table = "trades"

    def __str__(self):
        return f"{self.side} {self.quantity} {self.ticker} @ {self.price}"


class Order(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    trade = models.ForeignKey(Trade, on_delete=models.CASCADE, related_name="orders")
    order_type = models.CharField(max_length=10, choices=Trade.OrderType.choices)
    status = models.CharField(max_length=10, choices=Trade.Status.choices, default="PENDING")
    broker_order_id = models.CharField(max_length=50, null=True, blank=True)
    quantity = models.DecimalField(max_digits=15, decimal_places=6)
    price = models.DecimalField(max_digits=15, decimal_places=6)
    filled_quantity = models.DecimalField(max_digits=15, decimal_places=6, default=0)
    fill_price = models.DecimalField(max_digits=15, decimal_places=6, null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    filled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "orders"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order {self.order_type} {self.quantity} @ {self.price} [{self.status}]"


class AccountConfig(models.Model):
    class Broker(models.TextChoices):
        MT4 = "MT4", "MetaTrader 4"
        MT5 = "MT5", "MetaTrader 5"

    class AccountType(models.TextChoices):
        CENT = "CENT", "Cent"
        STANDARD = "STANDARD", "Standard"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="account_configs")
    broker = models.CharField(max_length=4, choices=Broker.choices, default=Broker.MT5)
    account_type = models.CharField(max_length=8, choices=AccountType.choices, null=True, blank=True)
    account_number = models.CharField(max_length=20, blank=True)
    balance = models.DecimalField(max_digits=15, decimal_places=6, default=0)
    equity = models.DecimalField(max_digits=15, decimal_places=6, default=0)
    margin = models.DecimalField(max_digits=15, decimal_places=6, default=0)
    free_margin = models.DecimalField(max_digits=15, decimal_places=6, default=0)
    leverage = models.IntegerField(default=100)
    currency = models.CharField(max_length=3, default="USD")
    is_connected = models.BooleanField(default=False)
    simulation_mode = models.BooleanField(default=True)
    last_synced = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "account_configs"

    def __str__(self):
        return f"{self.broker} {self.account_number} ({self.currency})"


class Position(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="positions")
    ticker = models.CharField(max_length=20, unique=True)
    quantity = models.DecimalField(max_digits=15, decimal_places=6)
    avg_entry_price = models.DecimalField(max_digits=15, decimal_places=6)
    current_price = models.DecimalField(max_digits=15, decimal_places=6, default=0)
    unrealized_pnl = models.DecimalField(max_digits=15, decimal_places=6, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "positions"

    def __str__(self):
        return f"{self.ticker}: {self.quantity} @ {self.avg_entry_price}"


class LegendaryModuleResult(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="legendary_results")
    ticker = models.CharField(max_length=20)
    module_name = models.CharField(max_length=100)
    score = models.FloatField()
    recommendation = models.CharField(max_length=20)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        db_table = "legendary_module_results"

    def __str__(self):
        return f"{self.module_name} - {self.ticker}: {self.recommendation} ({self.score:.2f})"
