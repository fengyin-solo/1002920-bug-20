"""培训考核接口：维护培训记录，覆盖组织培训、整批送审、考核方式重发与归档。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import (
    ActionResult,
    BatchActionResult,
    BatchAssessmentPayload,
    EntryPayload,
    PageResult,
)
from app.services.training import TrainingService

router = APIRouter(prefix="/api/training", tags=["培训考核"])

service = TrainingService()

LIST_FIELDS = ["培训编号", "人员编号", "姓名", "培训内容", "培训对象", "培训日期", "培训讲师", "考核方式", "考核结果", "培训状态", "退回原因"]
STATUSES = ["待培训", "培训中", "考核退回", "已考核", "已归档"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按培训编号检索"),
    status: str | None = Query(default=None, description="待培训、培训中、考核退回、已考核、已归档"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1),
) -> PageResult[dict]:
    """按培训编号与状态过滤培训考核列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/stats")
def get_stats() -> dict[str, int]:
    """培训考核统计：待考核、已考核、退回数与合格率。"""
    return service.stats()


@router.get("/candidates", response_model=PageResult[dict])
def list_candidates(
    content: str | None = Query(default=None, description="按培训内容过滤本批人员"),
    keyword: str | None = Query(default=None, description="按人员编号/姓名/培训编号检索"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1),
) -> PageResult[dict]:
    """带出可排入下一批的人员名单；已经考过的不再出现。"""
    items, total = service.list_candidates(content=content, keyword=keyword, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.post("/batch-assess", response_model=BatchActionResult)
def batch_assess(payload: BatchAssessmentPayload) -> BatchActionResult:
    """整批提交考核结果：一批人作为一件事处理，逐条给出通过/退回/暂挂/跳过结果。

    带相同 batch_no 重发时原样返回上次处理结果，不重复落记录。
    """
    # 批次号重发先走幂等返回，再校验本批是否勾选人员。
    if payload.batch_no and service.get_batch(payload.batch_no) is not None:
        return BatchActionResult(**service.get_batch(payload.batch_no))
    if not payload.items:
        raise HTTPException(status_code=400, detail="本批没有勾选任何人员，无法送审")
    items = [item.model_dump() for item in payload.items]
    result = service.submit_batch(items, batch_no=payload.batch_no)
    return BatchActionResult(**result)


@router.get("/batches/{batch_no}")
def get_batch(batch_no: str) -> dict[str, Any]:
    """批次详情：整批每条的处理去向与失败原因都留在这一页。"""
    batch = service.get_batch(batch_no)
    if batch is None:
        raise HTTPException(status_code=404, detail=f"批次 {batch_no} 不存在")
    return batch


@router.post("/{entry_id}/exam-method/retry", response_model=ActionResult)
def retry_exam_method(entry_id: int) -> ActionResult:
    """考核方式取不到时单条重发；成功回填，失败原因留在记录详情页。"""
    entry, message = service.refresh_exam_method(entry_id)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


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
    """对单条培训记录执行组织培训、归档；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
