#!/usr/bin/env python
"""CLI stats report: `python stats_report.py [days]` (default 7)."""

import sys

from flowspeech.config import load_config
from flowspeech.stats import StatsStore


def main() -> None:
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    config = load_config()
    summary = StatsStore(config.data_dir).summary(days=days)

    print(f"=== FlowSpeech: статистика за {days} дн. ===")
    print(f"Диктовок:          {summary.total_sessions}")
    print(f"Слов надиктовано:  {summary.total_words}")
    print(f"Время речи:        {summary.total_speaking_sec / 60:.1f} мин")
    print(f"Средняя скорость:  {summary.average_wpm} слов/мин")

    if summary.top_words:
        print("\nТоп-20 слов:")
        for word, count in summary.top_words:
            print(f"  {word:<20} {count}")

    if summary.words_by_app:
        print("\nСлова по приложениям:")
        for app, count in summary.words_by_app:
            print(f"  {app:<20} {count}")


if __name__ == "__main__":
    main()
