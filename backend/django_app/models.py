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
        EXECUTED = "EXECUTED", "Executed"
        CANCELLED = "CANCELLED", "Cancelled"
        FAILED = "FAILED", "Failed"

    class Side(models.TextChoices):
        BUY = "BUY", "Buy"
        SELL = "SELL", "Sell"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="trades")
    ticker = models.CharField(max_length=20)
    side = models.CharField(max_length=4, choices=Side.choices)
    quantity = models.DecimalField(max_digits=15, decimal_places=6)
    price = models.DecimalField(max_digits=15, decimal_places=6)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    consensus = models.ForeignKey(ConsensusResult, on_delete=models.SET_NULL, null=True, blank=True)
    executed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        db_table = "trades"

    def __str__(self):
        return f"{self.side} {self.quantity} {self.ticker} @ {self.price}"


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
