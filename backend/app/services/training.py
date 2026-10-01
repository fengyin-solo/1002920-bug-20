"""培训考核业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "training"
REQUIRED_FIELDS = ["培训编号", "培训内容", "培训对象"]
STATUS_ORDER = ["待培训", "培训中", "已退回", "已考核", "已归档"]
ACTION_RULES = {"组织培训": "培训中", "组织考核": "已考核", "归档": "已归档"}
NEGATIVE_ACTIONS = []

# 允许提交考核结果的状态；已考核、已归档视为"已考过"，重复提交时跳过而不是再录一次
ASSESSABLE_STATUSES = {"待培训", "培训中", "已退回"}
SETTLED_STATUSES = {"已考核", "已归档"}
RESULT_OPTIONS = ("通过", "不通过")


class TrainingService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [
                row for row in rows
                if keyword in str(row.get("培训编号", "")) or keyword in str(row.get("培训对象", ""))
            ]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def stats(self) -> dict[str, int]:
        """列表页统计卡：各状态条数与合格率，全部按当前数据实算。"""
        rows = store.rows(MODULE)
        counts = {status: 0 for status in STATUS_ORDER}
        passed = 0
        graded = 0
        for row in rows:
            status = str(row.get("status") or "")
            if status in counts:
                counts[status] += 1
            result = str(row.get("考核结果") or "").strip()
            if result in RESULT_OPTIONS:
                graded += 1
                if result == "通过":
                    passed += 1
        return {
            "待考核": counts["待培训"] + counts["培训中"] + counts["已退回"],
            "已考核": counts["已考核"],
            "已退回": counts["已退回"],
            "合格率": round(passed * 100 / graded) if graded else 0,
        }

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"培训记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于培训考核可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"培训记录已{action}"

    def assessment_context(self, entry_ids: list[int]) -> list[dict[str, Any]]:
        """批量面板的预填数据：逐条带出培训内容与考核方式，并标注能否进入本批。"""
        context: list[dict[str, Any]] = []
        for entry_id in entry_ids:
            entry = store.find(MODULE, entry_id)
            if entry is None:
                context.append({
                    "id": entry_id,
                    "eligible": False,
                    "note": "培训记录不存在或已删除",
                })
                continue
            status = str(entry.get("status") or "")
            eligible = status in ASSESSABLE_STATUSES
            note = ""
            if status in SETTLED_STATUSES:
                note = "已考核，不会重复排进本批"
            elif not eligible:
                note = f"当前状态「{status}」暂不能提交考核"
            context.append({
                "id": entry_id,
                "培训编号": entry.get("培训编号"),
                "培训对象": entry.get("培训对象"),
                "培训内容": entry.get("培训内容"),
                "培训日期": entry.get("培训日期"),
                "考核方式": entry.get("考核方式") or "",
                "status": status,
                "eligible": eligible,
                "note": note,
            })
        return context

    def submit_assessments(
        self, items: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], dict[str, int]]:
        """成批提交考核结果：整批一次受理，逐条给出回执，单条失败不影响其余入档。"""
        receipts: list[dict[str, Any]] = []
        summary = {"received": len(items), "passed": 0, "returned": 0, "skipped": 0, "failed": 0}
        for item in items:
            receipt = self._assess_one(item)
            receipts.append(receipt)
            outcome = receipt["outcome"]
            if outcome == "已入档":
                summary["passed"] += 1
            elif outcome == "已退回":
                summary["returned"] += 1
            elif outcome == "已跳过":
                summary["skipped"] += 1
            else:
                summary["failed"] += 1
        return receipts, summary

    def _assess_one(self, item: dict[str, Any]) -> dict[str, Any]:
        receipt: dict[str, Any] = {
            "entry_id": item.get("entry_id"),
            "培训编号": None,
            "培训对象": None,
            "ok": False,
            "outcome": "待补正",
            "message": "",
        }
        entry = store.find(MODULE, int(receipt["entry_id"] or 0))
        if entry is None:
            receipt["message"] = f"培训记录 {receipt['entry_id']} 不存在，无法提交考核"
            return receipt
        receipt["培训编号"] = entry.get("培训编号")
        receipt["培训对象"] = entry.get("培训对象")

        status = str(entry.get("status") or "")
        if status in SETTLED_STATUSES:
            receipt.update(ok=True, outcome="已跳过", message="该人员已考核，不再重复排进本批")
            return receipt
        if status not in ASSESSABLE_STATUSES:
            receipt["message"] = f"当前状态「{status}」不允许提交考核结果"
            return receipt

        result = str(item.get("考核结果") or "").strip()
        if result not in RESULT_OPTIONS:
            receipt["message"] = "考核结果需为「通过」或「不通过」"
            return receipt

        method = str(item.get("考核方式") or "").strip() or str(entry.get("考核方式") or "").strip()
        if not method:
            receipt["message"] = "取不到考核方式，请补录后重发"
            return receipt

        if result == "不通过":
            reason = str(item.get("退回原因") or "").strip()
            if not reason:
                receipt["message"] = "考核不通过的记录必须写明退回原因"
                return receipt
            entry["考核结果"] = result
            entry["考核方式"] = method
            entry["退回原因"] = reason
            entry["status"] = "已退回"
            entry["pending"] = True
            entry["abnormal"] = True
            receipt.update(ok=True, outcome="已退回", message=f"考核不通过，已单独退回：{reason}")
            return receipt

        entry["考核结果"] = result
        entry["考核方式"] = method
        exam_date = str(item.get("考核日期") or "").strip()
        if exam_date:
            entry["考核日期"] = exam_date
        entry.pop("退回原因", None)
        entry["status"] = "已考核"
        entry["pending"] = False
        entry["abnormal"] = False
        receipt.update(ok=True, outcome="已入档", message="考核通过，结果已落入记录")
        return receipt
