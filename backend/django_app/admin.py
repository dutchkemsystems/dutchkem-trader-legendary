from django.contrib import admin
from .models import AnalystResult, ConsensusResult, Trade, Position, LegendaryModuleResult


@admin.register(AnalystResult)
class AnalystResultAdmin(admin.ModelAdmin):
    list_display = ("ticker", "analyst_type", "signal", "confidence", "created_at")
    list_filter = ("analyst_type", "signal")
    search_fields = ("ticker",)


@admin.register(ConsensusResult)
class ConsensusResultAdmin(admin.ModelAdmin):
    list_display = ("ticker", "consensus_signal", "weight", "created_at")
    list_filter = ("consensus_signal",)
    search_fields = ("ticker",)


@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    list_display = ("ticker", "side", "quantity", "price", "status", "created_at")
    list_filter = ("status", "side")
    search_fields = ("ticker",)


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ("ticker", "quantity", "avg_entry_price", "current_price", "unrealized_pnl")
    search_fields = ("ticker",)


@admin.register(LegendaryModuleResult)
class LegendaryModuleResultAdmin(admin.ModelAdmin):
    list_display = ("module_name", "ticker", "score", "recommendation", "created_at")
    list_filter = ("module_name", "recommendation")
    search_fields = ("ticker", "module_name")
