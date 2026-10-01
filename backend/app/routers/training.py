"""培训考核接口：维护培训记录，覆盖组织培训、组织考核、归档与成批提交考核结果。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import (
    ActionResult,
    AssessmentBatchPayload,
    AssessmentBatchResult,
    AssessmentReceipt,
    EntryPayload,
    PageResult,
)
from app.services.training import STATUS_ORDER, TrainingService

router = APIRouter(prefix="/api/training", tags=["培训考核"])

service = TrainingService()

LIST_FIELDS = ["培训编号", "培训内容", "培训对象", "培训日期", "培训讲师", "考核方式", "考核结果", "培训状态"]
STATUSES = STATUS_ORDER


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按培训编号或培训对象检索"),
    status: str | None = Query(default=None, description="待培训、培训中、已退回、已考核、已归档"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按培训编号与状态过滤培训考核列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/stats")
def get_stats() -> dict[str, int]:
    """列表页统计卡：待考核、已考核、已退回条数与合格率。"""
    return service.stats()


@router.get("/assessment-context")
def assessment_context(
    ids: str = Query(..., description="逗号分隔的记录 id，如 1,2,3"),
) -> dict[str, Any]:
    """批量考核面板的预填数据：逐条带出培训内容与考核方式；取不到时前端可原样重发。"""
    entry_ids = [int(part) for part in ids.split(",") if part.strip().isdigit()]
    if not entry_ids:
        raise HTTPException(status_code=400, detail="请先勾选要参加本批考核的培训记录")
    return {"items": service.assessment_context(entry_ids)}


@router.post("/assessments/batch", response_model=AssessmentBatchResult)
def submit_assessments(payload: AssessmentBatchPayload) -> AssessmentBatchResult:
    """成批提交考核结果：整批当成一件事受理，逐条回执；不通过的单独退回并写明原因。"""
    items = [item.model_dump() for item in payload.items]
    if not items:
        return AssessmentBatchResult(ok=False, message="本批没有可提交的考核记录")
    receipts, summary = service.submit_assessments(items)
    message = (
        f"本批 {summary['received']} 条：入档 {summary['passed']} 条、"
        f"退回 {summary['returned']} 条、跳过 {summary['skipped']} 条、"
        f"待补正 {summary['failed']} 条"
    )
    return AssessmentBatchResult(
        ok=summary["failed"] == 0,
        message=message,
        summary=summary,
        results=[AssessmentReceipt(**receipt) for receipt in receipts],
    )


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出培训考核清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "training", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条培训记录明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"培训记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条培训记录，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="培训记录已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条培训记录执行组织培训、组织考核、归档；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
