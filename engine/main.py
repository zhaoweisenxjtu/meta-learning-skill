#!/usr/bin/env python3
"""Meta-Learning Engine CLI

多用户、多路线、程序化的元学习引擎。
数据存储在 SQLite，算法驱动而非对话记忆驱动。

Usage:
    meta-learn user create <name>
    meta-learn track create <user-id> <name> --type <exam|applied|interest>
    meta-learn node add <track-id> <name>
    meta-learn review create <node-id> --quality <0-5>
    meta-learn workflow get-next <track-id>
    meta-learn schedule today --user <id>
    meta-learn report dashboard <user-id>
    ...
"""

import argparse
import json
import sys
import os
from datetime import date, datetime
from pathlib import Path

# 确保能找到 engine 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.db.database import init_db, get_connection
from engine.db import dao_user, dao_track, dao_node, dao_review, dao_assessment, dao_journal
from engine.db.migrate_from_json import JsonMigrator
from engine.core.sm2 import SM2Calculator
from engine.core.fake_detection import FakeDetector
from engine.core.indicators import Dashboard
from engine.core.knowledge_quality import KnowledgeQualityAssessor, cli_assess
from engine.workflow.state_machine import (
    get_next_recommended, get_guarded_next, is_valid_transition,
    get_allowed_transitions, get_state_label,
)
from engine.scheduler.multi_track import MultiTrackScheduler


def json_output(data):
    """Print output as JSON and exit."""
    print(json.dumps(data, ensure_ascii=False, indent=2))
    sys.exit(0)


def md_output(text: str):
    """Print Markdown output."""
    print(text)


# ──────────────────────────────────────────────
# User Commands
# ──────────────────────────────────────────────

def cmd_user_create(args):
    user = dao_user.create_user(args.name, args.display_name or args.name)
    if args.json:
        json_output(user)
    md_output(f"用户创建成功: **{user['name']}** (ID: {user['id']})")


def cmd_user_list(args):
    users = dao_user.list_users()
    if args.json:
        json_output(users)
    if not users:
        md_output("暂无用户。")
        return
    lines = ["## 用户列表\n", "| ID | 名称 | 路线数 | 创建时间 |"]
    lines.append("|----|------|--------|---------|")
    conn = get_connection()
    for u in users:
        cnt = conn.execute("SELECT COUNT(*) AS c FROM tracks WHERE user_id=?", (u["id"],)).fetchone()["c"]
        lines.append(f"| {u['id']} | {u['name']} | {cnt} | {u['created_at']} |")
    conn.close()
    md_output("\n".join(lines))


def cmd_user_delete(args):
    ok = dao_user.delete_user(args.user_id)
    if args.json:
        json_output({"deleted": ok})
    md_output(f"用户 {'已删除' if ok else '未找到'}.")


# ──────────────────────────────────────────────
# Track Commands
# ──────────────────────────────────────────────

def cmd_track_create(args):
    track = dao_track.create_track(args.user_id, args.name, args.type, args.priority)
    if args.json:
        json_output(track)
    state_label = get_state_label(track["current_state"])
    md_output(
        f"路线创建成功: **{track['name']}**\n"
        f"- ID: {track['id']} | 类型: {track['target_type']} | 优先级: {track['priority']}\n"
        f"- 状态: {state_label}"
    )


def cmd_track_list(args):
    tracks = dao_track.list_tracks(args.user_id, args.status)
    if args.json:
        json_output(tracks)
    if not tracks:
        md_output("暂无学习路线。")
        return
    lines = ["## 学习路线\n", "| ID | 名称 | 类型 | 状态 | 优先级 | 进度 | 创建时间 |"]
    lines.append("|----|------|------|------|--------|------|---------|")
    for t in tracks:
        state_label = get_state_label(t["current_state"])
        lines.append(
            f"| {t['id']} | {t['name']} | {t['target_type']} "
            f"| {t['status']} | {t['priority']} | {state_label} | {t['created_at']} |"
        )
    md_output("\n".join(lines))


def cmd_track_update(args):
    updates = {}
    if args.name:
        updates["name"] = args.name
    if args.status:
        updates["status"] = args.status
    if args.priority is not None:
        updates["priority"] = args.priority
    track = dao_track.update_track(args.track_id, **updates)
    if args.json:
        json_output(track)
    md_output(f"路线已更新: **{track['name']}** (ID: {track['id']})")


# ──────────────────────────────────────────────
# Node Commands
# ──────────────────────────────────────────────

def cmd_node_add(args):
    node = dao_node.add_node(args.track_id, args.name, args.description,
                             args.parent, args.importance, args.level)
    if args.json:
        json_output(node)
    md_output(f"节点已添加: **{node['name']}** (ID: {node['id']}, L{node['current_level']})")


def cmd_node_list(args):
    nodes = dao_node.list_nodes(args.track_id, args.status)
    if args.json:
        json_output(nodes)
    if not nodes:
        md_output("暂无知识节点。")
        return
    lines = ["## 知识节点\n", "| ID | 名称 | 层级 | 重要度 | 状态 | 下次复习 |"]
    lines.append("|----|------|------|--------|------|---------|")
    today = date.today().isoformat()
    for n in nodes:
        review_str = n["next_review"] or "-"
        if n["next_review"] and n["next_review"] <= today:
            review_str = f"**{n['next_review']}** (逾期)"
        lines.append(
            f"| {n['id']} | {n['name']} | L{n['current_level']} "
            f"| {n['importance']} | {n['status']} | {review_str} |"
        )
    md_output("\n".join(lines))


def cmd_node_update(args):
    updates = {}
    if args.name:
        updates["name"] = args.name
    if args.level is not None:
        updates["current_level"] = args.level
    if args.status:
        updates["status"] = args.status
    node = dao_node.update_node(args.node_id, **updates)
    if args.json:
        json_output(node)
    md_output(f"节点已更新: **{node['name']}** (L{node['current_level']})")


def cmd_node_delete(args):
    ok = dao_node.delete_node(args.node_id)
    if args.json:
        json_output({"deleted": ok})
    md_output(f"节点 {'已删除' if ok else '未找到'}.")


def cmd_node_content(args):
    """View or update node content."""
    if args.content is not None:
        node = dao_node.update_node_content(
            args.node_id, args.content,
            source_url=args.source_url or "",
            source_title=args.source_title or "",
            quality_score=args.quality or 0,
            tags=args.tags,
        )
        # Update quality fields if provided
        if node and (args.node_type or args.theory is not None or args.data is not None or args.method is not None):
            conn = get_connection()
            try:
                updates = []
                params = []
                if args.node_type:
                    updates.append("node_type = ?")
                    params.append(args.node_type)
                if args.theory is not None:
                    updates.append("theory_level = ?")
                    params.append(args.theory)
                if args.data is not None:
                    updates.append("data_level = ?")
                    params.append(args.data)
                if args.method is not None:
                    updates.append("method_level = ?")
                    params.append(args.method)
                if updates:
                    updates.append("updated_at = date('now')")
                    params.append(args.node_id)
                    conn.execute(f"UPDATE knowledge_nodes SET {', '.join(updates)} WHERE id = ?", params)
                    conn.commit()
            finally:
                conn.close()
        if args.json:
            json_output(node)
        md_output(f"内容已更新: **{node['name']}** (ID: {node['id']})")
        return

    if args.file:
        try:
            node = dao_node.import_node_content(args.node_id, args.file)
        except FileNotFoundError as e:
            md_output(f"错误: {e}")
            sys.exit(1)
        if args.json:
            json_output(node)
        md_output(f"文件已导入: **{node['name']}** (来源: {args.file})")
        return

    # View mode
    node = dao_node.get_node(args.node_id)
    if not node:
        md_output(f"错误: 节点 {args.node_id} 不存在。")
        sys.exit(1)
    if args.json:
        json_output(node)
        return

    has_content = bool(node.get("content"))
    quality = node.get("quality_score", 0)
    quality_label = {0: "未评估", 1: "低", 2: "偏低", 3: "可用", 4: "良好", 5: "优秀"}
    # NUSAP quality info
    theory = node.get("theory_level", 0)
    data = node.get("data_level", 0)
    method = node.get("method_level", 0)
    nusap_str = f"(T:{theory}, D:{data}, M:{method})" if (theory or data or method) else ""
    md_output(
        f"## {node['name']} (ID: {node['id']})\n"
        f"- 路线: {node['track_id']} | 层级: L{node['current_level']} | 重要度: {node['importance']}\n"
        f"- 内容质量: {quality_label.get(quality, '?')} ({quality}/5) {nusap_str}\n"
        f"- 来源: {node.get('source_title', '-') or '-'}\n"
        + (f"- 来源 URL: {node['source_url']}\n" if node.get("source_url") else "")
        + (f"- 标签: {node.get('tags', '[]')}\n" if node.get("tags", "[]") != "[]" else "")
        + (f"- 缓存时间: {node.get('cached_at', '-')}\n" if node.get("cached_at") else "")
        + "\n---\n" + (node["content"] if has_content else "*无内容*")
    )


def cmd_node_search(args):
    """Full-text search across node names and content."""
    results = dao_node.search_nodes(args.keyword, args.track_id, args.limit)
    if args.json:
        json_output(results)
    if not results:
        md_output(f"未找到包含「{args.keyword}」的节点。")
        return
    lines = [f"## 搜索结果: 「{args.keyword}」\n", "| ID | 名称 | 路线 | 质量 | 层级 |"]
    lines.append("|----|------|------|------|------|")
    conn = get_connection()
    for n in results:
        track = conn.execute("SELECT name FROM tracks WHERE id=?", (n["track_id"],)).fetchone()
        track_name = track["name"] if track else "?"
        quality_str = f"{n['quality_score']}/5" if n.get("quality_score") else "-"
        lines.append(
            f"| {n['id']} | {n['name']} | {track_name} "
            f"| {quality_str} | L{n['current_level']} |"
        )
    conn.close()
    lines.append(f"\n共 **{len(results)}** 条结果。")
    md_output("\n".join(lines))


# ──────────────────────────────────────────────
# Review Commands
# ──────────────────────────────────────────────

def cmd_review_create(args):
    """执行一次 SM-2 复习并更新节点。"""
    node = dao_node.get_node(args.node_id)
    if not node:
        md_output(f"错误: 节点 {args.node_id} 不存在。")
        sys.exit(1)

    result = SM2Calculator.compute(
        quality=args.quality,
        ef=node["ef"],
        interval_days=node["interval"],
        repetitions=node["repetitions"],
    )

    # 更新节点
    dao_node.update_node(
        args.node_id,
        ef=result["ef"],
        interval=result["interval_days"],
        repetitions=result["repetitions"],
        next_review=result["next_review"],
    )

    # 记录复习历史
    review = dao_review.create_review(
        node_id=args.node_id,
        quality=args.quality,
        ef_after=result["ef"],
        interval_after=result["interval_days"],
    )

    if args.json:
        json_output({"node": node["name"], **result, "review_id": review["id"]})

    quality_map = {0: "完全忘记", 1: "困难", 2: "勉强", 3: "一般", 4: "良好", 5: "完美"}
    status = "通过" if result["passed"] else "未通过"
    md_output(
        f"复习完成: **{node['name']}**\n"
        f"- 评分: {args.quality}/5 ({quality_map.get(args.quality, '未知')})\n"
        f"- 结果: {status}\n"
        f"- EF: {node['ef']} → {result['ef']}\n"
        f"- 间隔: {result['interval_days']} 天\n"
        f"- 下次复习: {result['next_review']}"
    )


def cmd_review_due(args):
    due = dao_node.get_due_nodes(args.track_id, args.user_id)
    if args.json:
        json_output(due)
    if not due:
        md_output("今日无到期复习！")
        return
    lines = ["## 今日待复习\n", "| ID | 节点名称 | 路线 | 上次间隔 | 重要度 |"]
    lines.append("|----|---------|------|---------|--------|")
    conn = get_connection()
    for n in due:
        track = conn.execute("SELECT name FROM tracks WHERE id=?", (n["track_id"],)).fetchone()
        track_name = track["name"] if track else "?"
        lines.append(
            f"| {n['id']} | {n['name']} | {track_name} | {n['interval']}天 | {n['importance']} |"
        )
    conn.close()
    lines.append(f"\n共 **{len(due)}** 项待复习。")
    md_output("\n".join(lines))


def cmd_review_stats(args):
    stats = dao_review.get_review_stats(args.track_id)
    if args.json:
        json_output(stats)
    md_output(
        f"## 复习统计\n"
        f"- 总复习次数: {stats['total_reviews']}\n"
        f"- 平均评分: {stats['avg_quality']}/5\n"
        f"- 平均 EF: {stats['avg_ef']}\n"
        f"- 通过率: {stats['pass_rate']*100 if stats['pass_rate'] else 0:.1f}%"
    )


# ──────────────────────────────────────────────
# Assessment Commands
# ──────────────────────────────────────────────

def cmd_assessment_log(args):
    assess = dao_assessment.log_assessment(
        user_id=args.user_id,
        track_id=args.track_id,
        level_after=args.after,
        level_before=args.before,
        node_id=args.node,
        methods=args.methods,
        duration_minutes=args.duration,
        notes=args.notes,
    )
    if args.json:
        json_output(assess)
    md_output(f"评估记录已保存 (ID: {assess['id']})")


def cmd_assessment_list(args):
    items = dao_assessment.list_assessments(args.track_id, args.user_id)
    if args.json:
        json_output(items)
    if not items:
        md_output("暂无评估记录。")
        return
    lines = ["## 评估记录\n", "| ID | 日期 | 节点 | L前→L后 | 用时 | 方法 |"]
    lines.append("|----|------|------|---------|------|------|")
    for a in items:
        node_name = ""
        if a["node_id"]:
            node = dao_node.get_node(a["node_id"])
            node_name = node["name"] if node else f"#{a['node_id']}"
        methods_str = ", ".join(json.loads(a["methods"])) if a["methods"] != "[]" else "-"
        lines.append(
            f"| {a['id']} | {a['created_at'][:10]} | {node_name} "
            f"| L{a['level_before']}→L{a['level_after']} | {a['duration_minutes']}min | {methods_str} |"
        )
    md_output("\n".join(lines))


def cmd_assessment_recent(args):
    recent = dao_assessment.get_recent_assessments(args.track_id, args.limit)
    if args.json:
        json_output(recent)
    cmd_assessment_list(args)  # reuse


# ──────────────────────────────────────────────
# Journal Commands
# ──────────────────────────────────────────────

def cmd_journal_create(args):
    entry = dao_journal.create_journal(
        user_id=args.user_id,
        date_str=args.date,
        focus_minutes=args.focus,
        diffuse_minutes=args.diffuse,
        topics=args.topics,
        methods=args.methods,
        highlights=args.highlights,
        struggles=args.struggles,
        tomorrow_plan=args.tomorrow,
    )
    if args.json:
        json_output(entry)
    md_output(f"学习日志已保存 ({entry['date']})")


def cmd_journal_get(args):
    entry = dao_journal.get_journal_by_date(args.user_id, args.date)
    if args.json:
        json_output(entry)
    if not entry:
        md_output(f"{args.date} 无学习日志。")
        return
    topics = ", ".join(json.loads(entry["topics"])) if entry["topics"] != "[]" else "-"
    methods = ", ".join(json.loads(entry["methods"])) if entry["methods"] != "[]" else "-"
    md_output(
        f"## 学习日志 — {entry['date']}\n"
        f"- 专注: {entry['focus_minutes']}min | 发散: {entry['diffuse_minutes']}min\n"
        f"- 内容: {topics}\n"
        f"- 方法: {methods}\n"
        f"- 亮点: {entry['highlights'] or '-'}\n"
        f"- 卡点: {entry['struggles'] or '-'}\n"
        f"- 明日计划: {entry['tomorrow_plan'] or '-'}"
    )


# ──────────────────────────────────────────────
# Workflow Commands
# ──────────────────────────────────────────────

def cmd_workflow_status(args):
    track = dao_track.get_track(args.track_id)
    if args.json:
        json_output(track)
    if not track:
        md_output(f"错误: 路线 {args.track_id} 不存在。")
        return
    label = get_state_label(track["current_state"])
    allowed = ", ".join(get_state_label(s) for s in get_allowed_transitions(track["current_state"]))
    md_output(
        f"## 工作流状态 — {track['name']}\n"
        f"- 当前阶段: **{label}**\n"
        f"- 可转换: {allowed or '无（已终态）'}\n"
        f"- 目标类型: {track['target_type']}\n"
        f"- 状态: {track['status']}"
    )


def cmd_workflow_get_next(args):
    track = dao_track.get_track(args.track_id)
    if not track:
        md_output(f"错误: 路线 {args.track_id} 不存在。")
        sys.exit(1)

    nodes = dao_node.list_nodes(args.track_id)
    result = get_guarded_next(track, nodes)
    if args.json:
        json_output(result)
    label = get_state_label(result["next_state"])
    md_output(
        f"推荐下一步: **{label}**\n"
        f"理由: {result['reason']}"
    )


def cmd_workflow_transition(args):
    track = dao_track.get_track(args.track_id)
    if not track:
        md_output(f"错误: 路线 {args.track_id} 不存在。")
        sys.exit(1)

    if not is_valid_transition(track["current_state"], args.to):
        md_output(
            f"错误: 不能从 `{track['current_state']}` 转换到 `{args.to}`。\n"
            f"允许的转换: {', '.join(get_allowed_transitions(track['current_state']))}"
        )
        sys.exit(1)

    track = dao_track.update_track(args.track_id, current_state=args.to)
    if args.json:
        json_output(track)
    label = get_state_label(args.to)
    md_output(f"状态已转换: **{label}**")


# ──────────────────────────────────────────────
# Schedule Commands
# ──────────────────────────────────────────────

def cmd_schedule_today(args):
    scheduler = MultiTrackScheduler()
    schedule = scheduler.get_schedule(args.user_id, args.minutes)
    if args.json:
        json_output(schedule)
    if not schedule.get("tracks"):
        md_output(schedule.get("message", "暂无安排。"))
        return

    lines = [f"## 今日学习安排 — {schedule['date']}\n"]
    lines.append(f"总可用时间: **{schedule['total_minutes']} 分钟**\n")
    lines.append("| 路线 | 优先级 | 急迫度 | 分配时间 | 复习 | 新学 | 活动 |")
    lines.append("|------|--------|--------|---------|------|------|------|")

    for t in schedule["tracks"]:
        acts = "; ".join(
            f"{a['type']}({'记' if a['type'] == 'review' else '学'}{a['count']})"
            for a in t["activities"]
        )
        lines.append(
            f"| {t['name']} | {t['priority']} | {t['urgency']:.2f} "
            f"| {t['allocation_minutes']}min | {t['due_reviews']} | {t['pending_nodes']} | {acts} |"
        )
    md_output("\n".join(lines))


def cmd_schedule_optimize(args):
    """同 today，但指定总时间。"""
    args.minutes = args.total_minutes
    cmd_schedule_today(args)


# ──────────────────────────────────────────────
# Report Commands
# ──────────────────────────────────────────────

def cmd_report_dashboard(args):
    dashboard = Dashboard()
    data = dashboard.overall(args.user_id)
    if args.json:
        json_output(data)
    md_output(
        f"## 学习仪表盘\n\n"
        f"```\n"
        f"[知识总量]  {data['total_nodes']} 个节点\n"
        f"[L3+ 占比]  {data['l3_plus_pct']}%\n"
        f"[按时复习]  {data['ontime_review_pct']}%\n"
        f"[月跃迁]    {data['monthly_jumps']} 次\n"
        f"[平均 EF]   {data['avg_ef']}\n"
        f"```"
    )


def cmd_report_track(args):
    dashboard = Dashboard()
    data = dashboard.track_summary(args.track_id)
    if args.json:
        json_output(data)
    if "error" in data:
        md_output(f"错误: {data['error']}")
        return
    level_str = ", ".join(f"L{k}: {v}" for k, v in data["level_distribution"].items())
    md_output(
        f"## 路线报告 — {data['track_name']}\n"
        f"- 类型: {data['target_type']} | 阶段: {get_state_label(data['current_state'])}\n"
        f"- 总节点: {data['total_nodes']} | 活跃: {data['active_nodes']} | 已掌握(L3+): {data['mastered_nodes']}\n"
        f"- 平均层级: {data['avg_level']:.1f}\n"
        f"- 待复习: {data['due_reviews']} 项\n"
        f"- 层级分布: {level_str or '暂无节点'}"
    )


def cmd_report_migration(args):
    migrator = JsonMigrator()
    report = migrator.report()
    if args.json:
        json_output(report)
    lines = ["## JSON 迁移报告\n"]
    if report["json_files_found"]:
        lines.append("找到以下 JSON 文件:")
        for f in report["json_files_found"]:
            lines.append(f"- [found] {f}")
        lines.append(f"\n预估可迁移节点数: {report['estimated_nodes']}")
        lines.append("\n执行迁移: `meta-learn report migration --execute`")
    else:
        lines.append("未找到旧版 JSON 数据文件。")
    if report["json_files_missing"]:
        lines.append("\n未找到:")
        for f in report["json_files_missing"]:
            lines.append(f"- [missing] {f}")
    md_output("\n".join(lines))


# ──────────────────────────────────────────────
# Quality Commands (v3)
# ──────────────────────────────────────────────

def cmd_quality_assess(args):
    """评估单个知识节点的质量。"""
    assessor = KnowledgeQualityAssessor()
    result = assessor.assess_node(args.node_id)
    if args.json:
        json_output(result)
    if "error" in result:
        md_output(f"错误: {result['error']}")
        return
    n = result["nusap"]
    q = result["quality"]
    f = result.get("quality", {}).get("freshness", {})
    freshness_label = {"fresh": "✅ 有效", "expiring_soon": "⚠️ 即将过期", "stale": "❌ 已过期"}
    freshness_status = freshness_label.get(f.get("status", ""), "未知")
    days_remaining = f.get("days_remaining", "?")
    lines = [
        f"## 知识质量评估 — {result['node_name']}",
        f"- 节点类型: {result.get('node_type', 'concept')}",
        f"- 综合质量分: **{result['overall_score']}/100**",
        "",
        "### NUSAP Pedigree",
        f"- 理论支撑: {n['theory']['score']}/4 — {n['theory']['label']}",
        f"- 数据来源: {n['data']['score']}/4 — {n['data']['label']}",
        f"- 方法验证: {n['method']['score']}/4 — {n['method']['label']}",
        "",
        "### 数据层质量",
        f"- 完整性: {q['completeness']['score']}/4 — {q['completeness']['label']}",
        f"- 一致性: {q['consistency']['score']}/4 — {q['consistency']['label']}",
        f"- 来源可信度: {q['source_reliability']['score']}/4 — {q['source_reliability']['label']}",
        f"- 时效性: {freshness_status} (剩余{days_remaining}天)",
    ]
    if result["findings"]:
        lines.append("")
        lines.append("### 发现的问题")
        for finding in result["findings"]:
            lines.append(f"- ❌ {finding}")
    if result["recommendations"]:
        lines.append("")
        lines.append("### 改进建议")
        for rec in result["recommendations"]:
            lines.append(f"- 💡 {rec}")
    md_output("\n".join(lines))


def cmd_quality_assess_track(args):
    """评估整个路线的知识质量。"""
    assessor = KnowledgeQualityAssessor()
    result = assessor.assess_track(args.track_id)
    if args.json:
        json_output(result)
    if "error" in result:
        md_output(f"错误: {result['error']}")
        return
    dist = result["quality_distribution"]
    lines = [
        f"## 路线质量评估",
        f"- 总节点数: {result['total_nodes']}",
        f"- 平均质量分: **{result['average_quality_score']}/100**",
        f"- 质量分布: 优秀{dist['excellent']} 良好{dist['good']} 一般{dist['fair']} 差{dist['poor']}",
        "",
        "### 节点类型分布",
    ]
    for nt, cnt in result.get("node_type_distribution", {}).items():
        lines.append(f"- {nt}: {cnt}个")
    if result["top_findings"]:
        lines.append("")
        lines.append("### 主要问题")
        for f in result["top_findings"]:
            lines.append(f"- {f['finding']}（出现{f['count']}次）")
    md_output("\n".join(lines))


def cmd_quality_assess_all(args):
    """评估用户所有知识库的质量。"""
    assessor = KnowledgeQualityAssessor()
    result = assessor.assess_all(args.user_id)
    if args.json:
        json_output(result)
    if "error" in result:
        md_output(f"错误: {result['error']}")
        return
    lines = [
        f"## 全局知识质量评估",
        f"- 总路线数: {result['total_tracks']}",
        f"- 总节点数: {result['total_nodes']}",
        f"- 综合质量分: **{result['overall_quality_score']}/100**",
        "",
        "### 各路线质量",
    ]
    for t in result["tracks"]:
        dist = t["quality_distribution"]
        lines.append(f"- {t['track_name']}: {t['average_quality_score']}/100 ({t['total_nodes']}节点)")
    md_output("\n".join(lines))


def cmd_quality_report(args):
    """生成知识质量评估报告。"""
    assessor = KnowledgeQualityAssessor()
    report = assessor.generate_quality_report(args.user_id)
    md_output(report)


def cmd_quality_update(args):
    """更新节点质量评分。"""
    assessor = KnowledgeQualityAssessor()
    result = assessor.update_node_quality(
        node_id=args.node_id,
        audit_type=args.type or "review_update",
        theory_level=args.theory,
        data_level=args.data,
        method_level=args.method,
        source_reliability=args.source,
        completeness=args.completeness,
        consistency=args.consistency,
        notes=args.notes or "",
    )
    if args.json:
        json_output(result)
    if "error" in result:
        md_output(f"错误: {result['error']}")
        return
    md_output(
        f"质量评分已更新: **{result['quality_score']}/100**\n"
        f"NUSAP: (T:{result['nusap']['theory']}, D:{result['nusap']['data']}, M:{result['nusap']['method']})\n"
        f"审计类型: {result['audit_type']}"
    )


def cmd_quality_coverage(args):
    """评估知识库覆盖度。"""
    assessor = KnowledgeQualityAssessor()
    result = assessor.assess_coverage(args.track_id)
    if args.json:
        json_output(result)
    if "error" in result:
        md_output(f"错误: {result['error']}")
        return
    lines = [f"## 知识覆盖度评估\n"]
    lines.append("### 节点类型分布")
    for nt, info in result.get("node_type_distribution", {}).items():
        lines.append(f"- {info['label']}: {info['count']}个 ({info['priority']})")
    lines.append("")
    lines.append("### 深度分布")
    for level, cnt in sorted(result.get("depth_distribution", {}).items()):
        lines.append(f"- L{level}: {cnt}个")
    md_output("\n".join(lines))


def cmd_report_migration_exec(args):
    migrator = JsonMigrator()
    stats = migrator.migrate(
        user_name=args.user or "default_user",
        track_name=args.track or "默认学习路线",
    )
    if args.json:
        json_output(stats)
    lines = ["## 迁移完成\n"]
    lines.append(f"- 用户 ID: {stats.get('user_id', '-')}")
    lines.append(f"- 路线 ID: {stats.get('track_id', '-')}")
    lines.append(f"- 迁移节点: {stats['nodes']}")
    lines.append(f"- 迁移复习记录: {stats['reviews']}")
    lines.append(f"- 迁移评估记录: {stats['assessments']}")
    lines.append(f"- 迁移学习日志: {stats['journals']}")
    if stats["errors"]:
        lines.append("\n错误:")
        for e in stats["errors"]:
            lines.append(f"- [warn] {e}")
    md_output("\n".join(lines))


# ──────────────────────────────────────────────
# Argparse Setup
# ──────────────────────────────────────────────

def main():
    # Parse --json from sys.argv directly so it works with nested subcommands
    json_mode = "--json" in sys.argv
    if json_mode:
        sys.argv = [a for a in sys.argv if a != "--json"]

    parser = argparse.ArgumentParser(
        description="元学习引擎 CLI — 多用户多路线程序化学习管理",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出", default=False)
    sub = parser.add_subparsers(dest="command")

    # user
    p_user = sub.add_parser("user")
    p_user_sub = p_user.add_subparsers(dest="subcommand")
    p_user_create = p_user_sub.add_parser("create")
    p_user_create.add_argument("name")
    p_user_create.add_argument("--display-name")
    p_user_create.set_defaults(func=cmd_user_create)

    p_user_list = p_user_sub.add_parser("list")
    p_user_list.set_defaults(func=cmd_user_list)

    p_user_delete = p_user_sub.add_parser("delete")
    p_user_delete.add_argument("user_id", type=int)
    p_user_delete.set_defaults(func=cmd_user_delete)

    # track
    p_track = sub.add_parser("track")
    p_track_sub = p_track.add_subparsers(dest="subcommand")
    p_track_create = p_track_sub.add_parser("create")
    p_track_create.add_argument("user_id", type=int)
    p_track_create.add_argument("name")
    p_track_create.add_argument("--type", "-t", choices=["exam", "applied", "interest"], default="applied")
    p_track_create.add_argument("--priority", "-p", type=int, default=3, choices=range(1, 6))
    p_track_create.set_defaults(func=cmd_track_create)

    p_track_list = p_track_sub.add_parser("list")
    p_track_list.add_argument("user_id", type=int)
    p_track_list.add_argument("--status", choices=["active", "paused", "completed", "archived"])
    p_track_list.set_defaults(func=cmd_track_list)

    p_track_update = p_track_sub.add_parser("update")
    p_track_update.add_argument("track_id", type=int)
    p_track_update.add_argument("--name")
    p_track_update.add_argument("--status", choices=["active", "paused", "completed", "archived"])
    p_track_update.add_argument("--priority", type=int, choices=range(1, 6))
    p_track_update.set_defaults(func=cmd_track_update)

    # node
    p_node = sub.add_parser("node")
    p_node_sub = p_node.add_subparsers(dest="subcommand")
    p_node_add = p_node_sub.add_parser("add")
    p_node_add.add_argument("track_id", type=int)
    p_node_add.add_argument("name")
    p_node_add.add_argument("--description", "-d", default="")
    p_node_add.add_argument("--parent", type=int)
    p_node_add.add_argument("--importance", "-i", type=int, default=3, choices=range(1, 6))
    p_node_add.add_argument("--level", "-l", type=int, default=1, choices=range(1, 6))
    p_node_add.set_defaults(func=cmd_node_add)

    p_node_list = p_node_sub.add_parser("list")
    p_node_list.add_argument("track_id", type=int)
    p_node_list.add_argument("--status", choices=["active", "pending", "mastered", "archived"])
    p_node_list.set_defaults(func=cmd_node_list)

    p_node_update = p_node_sub.add_parser("update")
    p_node_update.add_argument("node_id", type=int)
    p_node_update.add_argument("--name")
    p_node_update.add_argument("--level", type=int, choices=range(1, 6))
    p_node_update.add_argument("--status", choices=["active", "pending", "mastered", "archived"])
    p_node_update.set_defaults(func=cmd_node_update)

    p_node_delete = p_node_sub.add_parser("delete")
    p_node_delete.add_argument("node_id", type=int)
    p_node_delete.set_defaults(func=cmd_node_delete)

    p_node_content = p_node_sub.add_parser("content")
    p_node_content.add_argument("node_id", type=int)
    p_node_content.add_argument("--content", help="设置正文内容 (Markdown)")
    p_node_content.add_argument("--file", help="从文件导入内容")
    p_node_content.add_argument("--source-url", help="来源 URL")
    p_node_content.add_argument("--source-title", help="来源标题")
    p_node_content.add_argument("--quality", type=int, choices=range(0, 6), help="内容质量评分 0-5")
    p_node_content.add_argument("--node-type", choices=["concept", "fact", "principle", "procedure", "framework", "case", "data_point", "reference"], help="节点类型")
    p_node_content.add_argument("--theory", type=int, choices=range(0, 5), help="理论支撑等级 0-4")
    p_node_content.add_argument("--data", type=int, choices=range(0, 5), help="数据来源等级 0-4")
    p_node_content.add_argument("--method", type=int, choices=range(0, 5), help="方法验证等级 0-4")
    p_node_content.add_argument("--tags", type=json.loads, help="标签数组 JSON")
    p_node_content.set_defaults(func=cmd_node_content)

    p_node_search = p_node_sub.add_parser("search")
    p_node_search.add_argument("keyword", help="搜索关键词")
    p_node_search.add_argument("--track", dest="track_id", type=int, help="按路线筛选")
    p_node_search.add_argument("--limit", type=int, default=20, help="最大结果数")
    p_node_search.set_defaults(func=cmd_node_search)

    # review
    p_review = sub.add_parser("review")
    p_review_sub = p_review.add_subparsers(dest="subcommand")
    p_review_create = p_review_sub.add_parser("create")
    p_review_create.add_argument("node_id", type=int)
    p_review_create.add_argument("--quality", "-q", type=int, required=True, choices=range(0, 6))
    p_review_create.set_defaults(func=cmd_review_create)

    p_review_due = p_review_sub.add_parser("due")
    p_review_due.add_argument("--track", dest="track_id", type=int)
    p_review_due.add_argument("--user", dest="user_id", type=int)
    p_review_due.set_defaults(func=cmd_review_due)

    p_review_stats = p_review_sub.add_parser("stats")
    p_review_stats.add_argument("--track", dest="track_id", type=int)
    p_review_stats.set_defaults(func=cmd_review_stats)

    # assessment
    p_assess = sub.add_parser("assessment")
    p_assess_sub = p_assess.add_subparsers(dest="subcommand")
    p_assess_log = p_assess_sub.add_parser("log")
    p_assess_log.add_argument("user_id", type=int)
    p_assess_log.add_argument("track_id", type=int)
    p_assess_log.add_argument("--after", type=int, required=True, choices=range(1, 6))
    p_assess_log.add_argument("--before", type=int, choices=range(1, 6))
    p_assess_log.add_argument("--node", type=int)
    p_assess_log.add_argument("--methods", type=json.loads, default=[])
    p_assess_log.add_argument("--duration", type=int, default=0)
    p_assess_log.add_argument("--notes", default="")
    p_assess_log.set_defaults(func=cmd_assessment_log)

    p_assess_list = p_assess_sub.add_parser("list")
    p_assess_list.add_argument("--track", dest="track_id", type=int)
    p_assess_list.add_argument("--user", dest="user_id", type=int)
    p_assess_list.set_defaults(func=cmd_assessment_list)

    p_assess_recent = p_assess_sub.add_parser("recent")
    p_assess_recent.add_argument("track_id", type=int)
    p_assess_recent.add_argument("--limit", type=int, default=5)
    p_assess_recent.set_defaults(func=cmd_assessment_recent)

    # journal
    p_journal = sub.add_parser("journal")
    p_journal_sub = p_journal.add_subparsers(dest="subcommand")
    p_journal_create = p_journal_sub.add_parser("create")
    p_journal_create.add_argument("user_id", type=int)
    p_journal_create.add_argument("--date", default=date.today().isoformat())
    p_journal_create.add_argument("--focus", type=int, default=0)
    p_journal_create.add_argument("--diffuse", type=int, default=0)
    p_journal_create.add_argument("--topics", type=json.loads, default=[])
    p_journal_create.add_argument("--methods", type=json.loads, default=[])
    p_journal_create.add_argument("--highlights", default="")
    p_journal_create.add_argument("--struggles", default="")
    p_journal_create.add_argument("--tomorrow", default="")
    p_journal_create.set_defaults(func=cmd_journal_create)

    p_journal_get = p_journal_sub.add_parser("get")
    p_journal_get.add_argument("user_id", type=int)
    p_journal_get.add_argument("--date", default=date.today().isoformat())
    p_journal_get.set_defaults(func=cmd_journal_get)

    # workflow
    p_wf = sub.add_parser("workflow")
    p_wf_sub = p_wf.add_subparsers(dest="subcommand")
    p_wf_status = p_wf_sub.add_parser("status")
    p_wf_status.add_argument("track_id", type=int)
    p_wf_status.set_defaults(func=cmd_workflow_status)

    p_wf_next = p_wf_sub.add_parser("get-next")
    p_wf_next.add_argument("track_id", type=int)
    p_wf_next.set_defaults(func=cmd_workflow_get_next)

    p_wf_trans = p_wf_sub.add_parser("transition")
    p_wf_trans.add_argument("track_id", type=int)
    p_wf_trans.add_argument("--to", required=True)
    p_wf_trans.set_defaults(func=cmd_workflow_transition)

    # schedule
    p_sched = sub.add_parser("schedule")
    p_sched_sub = p_sched.add_subparsers(dest="subcommand")
    p_sched_today = p_sched_sub.add_parser("today")
    p_sched_today.add_argument("--user", dest="user_id", type=int, required=True)
    p_sched_today.add_argument("--minutes", type=int)
    p_sched_today.set_defaults(func=cmd_schedule_today)

    p_sched_opt = p_sched_sub.add_parser("optimize")
    p_sched_opt.add_argument("user_id", type=int)
    p_sched_opt.add_argument("--total-minutes", type=int, required=True)
    p_sched_opt.set_defaults(func=cmd_schedule_optimize)

    # quality (v3)
    p_quality = sub.add_parser("quality")
    p_quality_sub = p_quality.add_subparsers(dest="subcommand")

    p_quality_assess = p_quality_sub.add_parser("assess")
    p_quality_assess.add_argument("node_id", type=int)
    p_quality_assess.set_defaults(func=cmd_quality_assess)

    p_quality_assess_track = p_quality_sub.add_parser("assess-track")
    p_quality_assess_track.add_argument("track_id", type=int)
    p_quality_assess_track.set_defaults(func=cmd_quality_assess_track)

    p_quality_assess_all = p_quality_sub.add_parser("assess-all")
    p_quality_assess_all.add_argument("user_id", type=int)
    p_quality_assess_all.set_defaults(func=cmd_quality_assess_all)

    p_quality_report = p_quality_sub.add_parser("report")
    p_quality_report.add_argument("user_id", type=int)
    p_quality_report.set_defaults(func=cmd_quality_report)

    p_quality_update = p_quality_sub.add_parser("update")
    p_quality_update.add_argument("node_id", type=int)
    p_quality_update.add_argument("--type", choices=["initial", "review_update", "source_verified", "freshness_check", "cross_validation", "expert_review"], default="review_update")
    p_quality_update.add_argument("--theory", type=int, choices=range(0, 5))
    p_quality_update.add_argument("--data", type=int, choices=range(0, 5))
    p_quality_update.add_argument("--method", type=int, choices=range(0, 5))
    p_quality_update.add_argument("--source", type=int, choices=range(0, 5))
    p_quality_update.add_argument("--completeness", type=int, choices=range(0, 5))
    p_quality_update.add_argument("--consistency", type=int, choices=range(0, 5))
    p_quality_update.add_argument("--notes", default="")
    p_quality_update.set_defaults(func=cmd_quality_update)

    p_quality_coverage = p_quality_sub.add_parser("coverage")
    p_quality_coverage.add_argument("track_id", type=int)
    p_quality_coverage.set_defaults(func=cmd_quality_coverage)

    # report
    p_report = sub.add_parser("report")
    p_report_sub = p_report.add_subparsers(dest="subcommand")
    p_report_dash = p_report_sub.add_parser("dashboard")
    p_report_dash.add_argument("user_id", type=int)
    p_report_dash.set_defaults(func=cmd_report_dashboard)

    p_report_track = p_report_sub.add_parser("track")
    p_report_track.add_argument("track_id", type=int)
    p_report_track.set_defaults(func=cmd_report_track)

    p_report_migrate = p_report_sub.add_parser("migration")
    p_report_migrate.set_defaults(func=cmd_report_migration)

    p_report_migrate_exec = p_report_sub.add_parser("migrate")
    p_report_migrate_exec.add_argument("--user", default="default_user")
    p_report_migrate_exec.add_argument("--track", default="默认学习路线")
    p_report_migrate_exec.set_defaults(func=cmd_report_migration_exec)

    args = parser.parse_args()

    # Init DB on any command
    init_db()

    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    # Pass --json flag to all functions via args
    args.json = json_mode
    args.func(args)


if __name__ == "__main__":
    main()
