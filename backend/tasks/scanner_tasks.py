# backend/tasks/scanner_tasks.py
from celery import shared_task
import asyncio
from apps.scanner.scanner import MultiTimeframeScanner

@shared_task
def run_full_scan(symbol: str):
    scanner = MultiTimeframeScanner()
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(scanner.scan(symbol))
        return {
            'symbol': result.symbol,
            'h1_bias': result.h1_bias,
            'alignment': result.alignment,
            'overall_signal': result.overall_signal,
            'overall_confidence': result.overall_confidence
        }
    except Exception as e:
        return {'error': f'Scan failed: {str(e)}'}
    finally:
        loop.close()
