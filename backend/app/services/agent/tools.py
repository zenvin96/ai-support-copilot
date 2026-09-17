"""本地工具：物流 mock。create_ticket / notify 是图节点，不交给 LLM 选择。"""
import random

from langchain_core.tools import tool

_MOCK = {
    123: {"carrier": None, "status": "not_shipped", "detail": "尚未出库，仓库缺货"},
    124: {"carrier": "顺丰", "status": "in_transit", "detail": "运输中，预计明日送达"},
    125: {"carrier": "圆通", "status": "delivered", "detail": "已签收"},
    126: {"carrier": None, "status": "not_shipped", "detail": "已支付，等待出库"},
}


@tool
def get_shipping_status(order_id: int) -> dict:
    """查询订单的物流状态（第三方物流 API mock）。参数 order_id 为订单号。"""
    info = _MOCK.get(int(order_id))
    if info is None:
        return {"order_id": order_id, "status": "unknown", "detail": "物流系统无此订单"}
    return {"order_id": order_id, **info, "eta_days": random.choice([1, 2, 3]) if info["status"] != "delivered" else 0}


LOCAL_TOOLS = [get_shipping_status]
