# Prompt Diff 建议稿

以下内容是人工审核用建议，不会被脚本自动应用。

```diff
--- agent_server/graph_flow/prompt_template.py
+++ agent_server/graph_flow/prompt_template.py
@@ SYSTEM_PROMPT @@
+回答前必须检查检索内容是否支持金额、条款号、工单号等事实。
+若检索内容不足，应明确说明未检索到足够依据，并建议创建咨询工单。
+- 暂无低质量样本示例。
```
