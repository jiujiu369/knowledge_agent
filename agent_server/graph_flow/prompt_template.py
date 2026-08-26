from __future__ import annotations


SYSTEM_PROMPT = """你是公司制度咨询智能体。只能基于检索到的制度片段和已存在工单回答。
如问题属于咨询、流程、报销、制度解释或故障处理，应建议创建咨询工单。
输出 JSON：{"answer":"...","needs_ticket":true或false,"title":"..."}。"""


def build_decision_messages(question: str, context: str) -> list[dict[str, str]]:
    """构建智能体决策`messages`。

    :param question: 函数处理所需的“问题”数据，类型为 ``str``。
    :param context: 函数处理所需的“`context`”数据，类型为 ``str``。
    :return: 返回构建智能体决策`messages`得到的结果，返回类型为 ``list[dict[str, str]]``。
    """
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"问题：{question}\n\n检索内容：\n{context}"},
    ]
