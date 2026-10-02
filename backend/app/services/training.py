"""培训考核业务规则：状态流转、字段校验、整批送审与考核方式获取都收在这里。

整批提交被当成一件事处理：
- 一个批次（batch）有唯一批次号，逐行处理、逐行留结果，绝不因中间一条卡住整批；
- 通过的行落入已考核记录，不通过的行单独退回并保留原因；
- 已考核人员不再进入下一批，批次号重发走幂等；
- 考核方式取自外部接口，取不到时保留失败原因、支持单条重发。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "training"
REQUIRED_FIELDS = ["培训编号", "培训内容", "培训对象"]
STATUS_ORDER = ["待培训", "培训中", "已考核", "已归档"]
ACTION_RULES = {"组织培训": "培训中", "组织考核": "已考核", "归档": "已归档"}
NEGATIVE_ACTIONS = []

# 只有这些状态的人员可以排进待考核批次；已考核/已归档不再重复排入。
BATCH_ELIGIBLE_STATUSES = {"培训中", "考核退回"}
ASSESS_RESULTS = {"通过", "不通过"}

# 培训内容 -> 考核方式 的常规映射，模拟外部考核方式登记接口的返回。
METHOD_BY_CONTENT = [
    ("锅炉", "笔试"),
    ("压力容器", "现场实操"),
    ("起重", "笔试+实操"),
    ("电梯", "现场实操"),
    ("场车", "笔试"),
    ("叉车", "笔试"),
]
DEFAULT_METHOD = "笔试"

# 外部接口暂时取不到考核方式的人员（按 人员编号+培训内容 定位）。
# 重发成功后从此清单移除，模拟接口恢复。
METHOD_UNAVAILABLE: set[tuple[str, str]] = {
    ("P-006", "压力容器应急处置"),
    ("P-010", "电梯应急救援"),
}


class ExamMethodGateway:
    """考核方式外部接口的本地模拟：会超时/返回空，也支持重发恢复。"""

    def fetch(self, person_id: str, content: str) -> str:
        if (person_id, content) in METHOD_UNAVAILABLE:
            raise RuntimeError(f"考核方式接口超时或返回空（{person_id} / {content}），请稍后重发")
        for keyword, method in METHOD_BY_CONTENT:
            if keyword in content:
                return method
        return DEFAULT_METHOD

    def retry(self, person_id: str, content: str) -> str:
        """重发：接口恢复后把该人员移出不可用清单并返回考核方式。"""
        try:
            method = self.fetch(person_id, content)
        except RuntimeError:
            METHOD_UNAVAILABLE.discard((person_id, content))
            method = self.fetch(person_id, content)
        return method


class TrainingService:
    def __init__(self) -> None:
        self.gateway = ExamMethodGateway()
        # 批次号 -> 批次处理留痕（重发同一批次号时原样返回，保证幂等）。
        self.batches: dict[str, dict[str, Any]] = {}
        self._batch_seq = 0

    # ---------- 列表与明细 ----------

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
            rows = [row for row in rows if keyword in str(row.get("培训编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        # total 在切片前统计，翻页后条数与总数始终对得上。
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def get_batch(self, batch_no: str) -> dict[str, Any] | None:
        return self.batches.get(batch_no)

    def stats(self) -> dict[str, int]:
        rows = store.rows(MODULE)
        assessed = [row for row in rows if row.get("status") == "已考核"]
        passed = [row for row in assessed if str(row.get("考核结果") or "") == "通过"]
        return {
            "待考核": sum(1 for row in rows if row.get("status") in BATCH_ELIGIBLE_STATUSES),
            "已考核": len(assessed),
            "考核退回": sum(1 for row in rows if row.get("status") == "考核退回"),
            "合格数": len(passed),
            "合格率": round(len(passed) * 100 / len(assessed)) if assessed else 0,
        }

    # ---------- 待考核名单 ----------

    def list_candidates(
        self,
        *,
        content: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[dict[str, Any]], int]:
        """带出可排入下一批的人员：已考核/已归档的名单不再出现。

        名单带出时逐条尝试获取考核方式；取不到的保留失败原因并标记待重发，
        不影响其他人员正常进入本批。
        """
        rows = [
            row for row in store.rows(MODULE)
            if row.get("status") in BATCH_ELIGIBLE_STATUSES
        ]
        if content:
            rows = [row for row in rows if content in str(row.get("培训内容") or "")]
        if keyword:
            rows = [
                row for row in rows
                if keyword in str(row.get("人员编号") or "")
                or keyword in str(row.get("姓名") or "")
                or keyword in str(row.get("培训编号") or "")
            ]
        total = len(rows)
        start = max(page - 1, 0) * size
        page_rows = rows[start:start + size]
        for row in page_rows:
            if not str(row.get("考核方式") or "").strip():
                self._ensure_exam_method(row)
        return page_rows, total

    # ---------- 登记与单条动作（保留原有入口） ----------

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        for field in ("人员编号", "姓名", "培训日期", "培训讲师", "考核方式"):
            if values.get(field):
                entry[field] = values[field]
        entry["status"] = STATUS_ORDER[0]
        entry["培训状态"] = STATUS_ORDER[0]
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
        entry["培训状态"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"培训记录已{action}"

    # ---------- 考核方式外部接口 ----------

    def _ensure_exam_method(self, row: dict[str, Any], *, retry: bool = False) -> str | None:
        """确保行上有考核方式；取不到时把失败原因留在记录上，供详情页展示。"""
        person_id = str(row.get("人员编号") or "")
        content = str(row.get("培训内容") or "")
        existing = str(row.get("考核方式") or "").strip()
        if existing and existing != "待获取":
            return existing
        try:
            method = self.gateway.retry(person_id, content) if retry else self.gateway.fetch(person_id, content)
        except RuntimeError as exc:
            row["考核方式"] = None
            row["考核方式失败原因"] = str(exc)
            return None
        row["考核方式"] = method
        row.pop("考核方式失败原因", None)
        return method

    def refresh_exam_method(self, entry_id: int) -> tuple[dict[str, Any] | None, str]:
        """取不到考核方式时单条重发；成功回填、失败把原因留在详情里。"""
        row = store.find(MODULE, entry_id)
        if row is None:
            return None, f"培训记录 {entry_id} 不存在或已归档"
        method = self._ensure_exam_method(row, retry=True)
        if method is None:
            return None, str(row.get("考核方式失败原因") or "考核方式仍未取到，请稍后再重发")
        return row, f"考核方式已重发获取：{method}"

    # ---------- 整批送审 ----------

    def _new_batch_no(self) -> str:
        self._batch_seq += 1
        stamp = datetime.now().strftime("%Y%m%d")
        return f"EXAM-{stamp}-{self._batch_seq:04d}"

    def _find_batch_row(self, item: dict[str, Any]) -> dict[str, Any] | None:
        if item.get("entry_id") is not None:
            row = store.find(MODULE, int(item["entry_id"]))
            if row is not None:
                return row
        person_id = str(item.get("人员编号") or "").strip()
        content = str(item.get("培训内容") or "").strip()
        if not person_id or not content:
            return None
        for row in store.rows(MODULE):
            if str(row.get("人员编号") or "") == person_id and str(row.get("培训内容") or "") == content:
                return row
        return None

    def submit_batch(
        self,
        items: list[dict[str, Any]],
        batch_no: str | None = None,
    ) -> dict[str, Any]:
        """把一整批考核结果当成一件事处理，逐行给出独立去向。"""
        # 同一批次号重发：原样返回上次结果，不重复落记录。
        if batch_no and batch_no in self.batches:
            return self.batches[batch_no]

        batch_no = batch_no or self._new_batch_no()
        results: list[dict[str, Any]] = []
        counts = {"passed": 0, "rejected": 0, "skipped": 0, "pending": 0}
        seen: set[int] = set()

        for item in items:
            result = str(item.get("考核结果") or "通过").strip() or "通过"
            reason = str(item.get("退回原因") or "").strip()
            row = self._find_batch_row(item)
            label = self._label_of(item, row)

            if row is None:
                outcome = self._item_result(batch_no, item, label, "rejected", "未找到对应的待考核培训记录，本条已退回")
            elif int(row.get("id", 0)) in seen:
                outcome = self._item_result(batch_no, item, label, "skipped", "同一批次内重复出现，只处理第一条")
            elif row.get("status") in {"已考核", "已归档"}:
                outcome = self._item_result(batch_no, item, label, "skipped", "该人员已考过，不再重复排进下一批")
            elif result not in ASSESS_RESULTS:
                outcome = self._item_result(batch_no, item, label, "rejected", f"考核结果「{result}」不合法，本条已退回")
            elif result == "不通过" and not reason:
                outcome = self._item_result(batch_no, item, label, "rejected", "考核不通过必须写明退回原因，本条已退回补填")
            else:
                seen.add(int(row["id"]))
                method = self._ensure_exam_method(row)
                if method is None:
                    outcome = self._item_result(
                        batch_no, item, label, "pending",
                        f"考核方式未取到：{row.get('考核方式失败原因')}；本条暂挂，可重发后再送审",
                    )
                elif result == "通过":
                    self._mark_passed(row, method, batch_no)
                    outcome = self._item_result(batch_no, item, label, "passed", f"考核通过，已落入记录（{method}）")
                else:
                    self._mark_rejected(row, method, reason, batch_no)
                    outcome = self._item_result(batch_no, item, label, "rejected", f"考核不通过，已单独退回：{reason}")
            results.append(outcome)
            counts[outcome["状态"]] += 1

        message = self._build_message(counts, len(items))
        batch = {
            "ok": counts["passed"] > 0 or counts["rejected"] > 0,
            "batch_no": batch_no,
            "total": len(items),
            "passed": counts["passed"],
            "rejected": counts["rejected"],
            "skipped": counts["skipped"],
            "pending": counts["pending"],
            "message": message,
            "items": results,
            "submitted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.batches[batch_no] = batch
        return batch

    @staticmethod
    def _label_of(item: dict[str, Any], row: dict[str, Any] | None) -> dict[str, Any]:
        return {
            "entry_id": row.get("id") if row is not None else item.get("entry_id"),
            "人员编号": (row.get("人员编号") if row is not None else None) or item.get("人员编号"),
            "姓名": row.get("姓名") if row is not None else None,
            "培训编号": row.get("培训编号") if row is not None else None,
            "培训内容": (row.get("培训内容") if row is not None else None) or item.get("培训内容"),
        }

    @staticmethod
    def _item_result(
        batch_no: str, item: dict[str, Any], label: dict[str, Any], status: str, message: str
    ) -> dict[str, Any]:
        return {
            **label,
            "批次号": batch_no,
            "考核结果": str(item.get("考核结果") or "通过"),
            "状态": status,
            "说明": message,
        }

    @staticmethod
    def _mark_passed(row: dict[str, Any], method: str, batch_no: str) -> None:
        row["status"] = "已考核"
        row["培训状态"] = "已考核"
        row["考核方式"] = method
        row["考核结果"] = "通过"
        row["退回原因"] = None
        row["批次号"] = batch_no
        row["pending"] = False
        row["abnormal"] = False

    @staticmethod
    def _mark_rejected(row: dict[str, Any], method: str, reason: str, batch_no: str) -> None:
        row["status"] = "考核退回"
        row["培训状态"] = "考核退回"
        row["考核方式"] = method
        row["考核结果"] = "不通过"
        row["退回原因"] = reason
        row["批次号"] = batch_no
        row["pending"] = True
        row["abnormal"] = True

    @staticmethod
    def _build_message(counts: dict[str, int], total: int) -> str:
        if total == 0:
            return "本批没有勾选任何人员，未产生考核结果"
        parts = [f"共处理 {total} 条"]
        if counts["passed"]:
            parts.append(f"{counts['passed']} 条通过并落入记录")
        if counts["rejected"]:
            parts.append(f"{counts['rejected']} 条不通过已单独退回")
        if counts["skipped"]:
            parts.append(f"{counts['skipped']} 条重复已跳过")
        if counts["pending"]:
            parts.append(f"{counts['pending']} 条考核方式缺失暂挂，可重发后再送审")
        return "，".join(parts)
