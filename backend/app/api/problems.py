"""题目级操作相关 API 端点。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ..auth.deps import require_user
from ..models import ProblemsResponse
from .deps import get_tasks_service

router = APIRouter(dependencies=[Depends(require_user)])


def _service(request: Request):
    """从通用 API 依赖中解析任务服务。"""
    return get_tasks_service(request)


@router.get("/problems", response_model=ProblemsResponse)
def list_problems(
    request: Request,
    subject: str | None = None,
    tag: str | None = None,
    source: str | None = Query(  # pylint: disable=unused-argument
        None, description="来源筛选（可重复传参，按 OR 逻辑匹配）"
    ),
    knowledge_tag: str | None = Query(  # pylint: disable=unused-argument
        None, description="知识点标签筛选（可重复传参，按 OR 逻辑匹配）"
    ),
    error_tag: str | None = Query(  # pylint: disable=unused-argument
        None, description="错因标签筛选（可重复传参，按 OR 逻辑匹配）"
    ),
    user_tag: str | None = Query(  # pylint: disable=unused-argument
        None, description="自定义标签筛选（可重复传参，按 OR 逻辑匹配）"
    ),
    created_after: str | None = Query(
        None, description="筛选在该日期之后创建的题目（ISO 8601 格式）"
    ),
    created_before: str | None = Query(
        None, description="筛选在该日期之前创建的题目（ISO 8601 格式）"
    ),
) -> ProblemsResponse:
    # FastAPI 会自动将重复查询参数聚合为列表
    # 这里直接读取原始 query params，以拿到全部值
    query_params = request.query_params
    source_list = query_params.getlist("source") if "source" in query_params else None
    knowledge_tag_list = (
        query_params.getlist("knowledge_tag")
        if "knowledge_tag" in query_params
        else None
    )
    error_tag_list = (
        query_params.getlist("error_tag") if "error_tag" in query_params else None
    )
    user_tag_list = (
        query_params.getlist("user_tag") if "user_tag" in query_params else None
    )

    svc = _service(request)
    return svc.list_problems(
        subject=subject,
        tag=tag,
        source=source_list,
        knowledge_tag=knowledge_tag_list,
        error_tag=error_tag_list,
        user_tag=user_tag_list,
        created_after=created_after,
        created_before=created_before,
    )
