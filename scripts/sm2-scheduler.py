#!/usr/bin/env python3
"""SM-2 间隔重复排期算法（已弃用，推荐使用 engine 中的 SM-2）。

SM-2 (SuperMemo 2) 是最广泛使用的间隔重复排期算法。
基于每次复习的质量评分动态调整复习间隔和难易度因子。

用法:
    python sm2-scheduler.py review <topic> <quality> [--data <path>]
    python sm2-scheduler.py schedule [--data <path>]
    python sm2-scheduler.py add <topic> [--data <path>]
    python sm2-scheduler.py list [--data <path>]
    python sm2-scheduler.py stats [--data <path>]

质量评分 (0-5):
    0 - 完全遗忘
    1 - 错误回答，但看到正确答案后能认出
    2 - 错误回答，但看到正确答案后感觉"应该想到"
    3 - 部分回忆，有困难或遗漏
    4 - 正确回忆，但有犹豫
    5 - 完美回忆，无需思考
"""

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# Fix encoding on Windows terminals
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_DATA_DIR = Path.home() / ".meta-learning"
DEFAULT_DATA_FILE = DEFAULT_DATA_DIR / "sm2-data.json"


class SM2Scheduler:
    def __init__(self, data_path: Path = DEFAULT_DATA_FILE):
        self.data_path = data_path
        self.entries: dict[str, dict] = {}
        self._load()

    def _load(self):
        if self.data_path.exists():
            try:
                self.entries = json.loads(self.data_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self.entries = {}

    def _save(self):
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        self.data_path.write_text(
            json.dumps(self.entries, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def add(self, topic: str) -> dict:
        if topic in self.entries:
            return self.entries[topic]
        entry = {
            "topic": topic,
            "ef": 2.5,           # 难易度因子 (E-Factor)，初始 2.5
            "interval": 1,        # 当前间隔（天）
            "repetitions": 0,     # 连续正确次数
            "next_review": str(date.today() + timedelta(days=1)),
            "history": [],
        }
        self.entries[topic] = entry
        self._save()
        return entry

    def review(self, topic: str, quality: int) -> dict:
        if topic not in self.entries:
            self.add(topic)
        entry = self.entries[topic]

        today = date.today()
        entry["history"].append({"date": str(today), "quality": quality})

        if quality >= 3:
            if entry["repetitions"] == 0:
                entry["interval"] = 1
            elif entry["repetitions"] == 1:
                entry["interval"] = 6
            else:
                entry["interval"] = round(entry["interval"] * entry["ef"])

            entry["repetitions"] += 1
        else:
            entry["repetitions"] = 0
            entry["interval"] = 1

        # 更新 EF 因子
        ef = entry["ef"] + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        entry["ef"] = max(1.3, ef)

        entry["next_review"] = str(today + timedelta(days=entry["interval"]))
        self._save()
        return entry

    def get_schedule(self) -> list[dict]:
        today = str(date.today())
        due = []
        for _topic, entry in self.entries.items():
            if entry["next_review"] <= today:
                due.append(entry)
        due.sort(key=lambda e: e["next_review"])
        return due

    def list_all(self) -> list[dict]:
        return sorted(self.entries.values(), key=lambda e: e["next_review"])

    def stats(self) -> dict:
        total = len(self.entries)
        if total == 0:
            return {"total_topics": 0}
        due = self.get_schedule()
        avg_ef = sum(e["ef"] for e in self.entries.values()) / total
        avg_interval = sum(e["interval"] for e in self.entries.values()) / total
        reviews_today = sum(
            1 for e in self.entries.values()
            if e["history"] and e["history"][-1]["date"] == str(date.today())
        )
        return {
            "total_topics": total,
            "due_today": len(due),
            "avg_ef": round(avg_ef, 2),
            "avg_interval_days": round(avg_interval, 1),
            "reviews_completed_today": reviews_today,
        }


def format_entry(entry: dict) -> str:
    return (
        f"[{entry['topic']}] "
        f"EF={entry['ef']:.2f} "
        f"间隔={entry['interval']}天 "
        f"连续正确={entry['repetitions']}次 "
        f"下次复习: {entry['next_review']}"
    )


def print_help():
    print(__doc__)


def main():
    if len(sys.argv) < 2:
        print_help()
        sys.exit(0)

    cmd = sys.argv[1]
    data_path = DEFAULT_DATA_FILE
    args = sys.argv[2:]

    # Parse --data flag
    for i, arg in enumerate(args):
        if arg == "--data" and i + 1 < len(args):
            data_path = Path(args[i + 1])
            args = [a for j, a in enumerate(args) if j not in (i, i + 1)]
            break

    scheduler = SM2Scheduler(data_path)

    if cmd == "add":
        if not args:
            print("用法: sm2-scheduler.py add <topic>")
            sys.exit(1)
        entry = scheduler.add(args[0])
        print(f"已添加: {format_entry(entry)}")

    elif cmd == "review":
        if len(args) < 2:
            print("用法: sm2-scheduler.py review <topic> <quality>")
            sys.exit(1)
        topic = args[0]
        try:
            quality = int(args[1])
        except ValueError:
            print("quality 必须是 0-5 的整数")
            sys.exit(1)
        if not 0 <= quality <= 5:
            print("quality 必须是 0-5 的整数")
            sys.exit(1)
        entry = scheduler.review(topic, quality)
        verdict = "PASS" if quality >= 3 else "RESET"
        print(f"评分 {quality} ({verdict}) → {format_entry(entry)}")

    elif cmd == "schedule":
        due = scheduler.get_schedule()
        if not due:
            print("今日无待复习项目。")
        else:
            print(f"今日待复习 ({len(due)} 项):")
            for entry in due:
                print(f"  {format_entry(entry)}")

    elif cmd == "list":
        entries = scheduler.list_all()
        if not entries:
            print("暂无学习项目。使用 'add' 添加。")
        else:
            for entry in entries:
                mark = "DUE" if entry["next_review"] <= str(date.today()) else "   "
                print(f"{mark} {format_entry(entry)}")

    elif cmd == "stats":
        s = scheduler.stats()
        print(f"总主题数: {s['total_topics']}")
        if s["total_topics"] > 0:
            print(f"今日待复习: {s['due_today']}")
            print(f"今日已完成: {s['reviews_completed_today']}")
            print(f"平均 EF: {s['avg_ef']}")
            print(f"平均间隔: {s['avg_interval_days']} 天")

    elif cmd in ("help", "-h", "--help"):
        print_help()

    else:
        print(f"未知命令: {cmd}")
        print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
