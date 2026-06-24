# 项目任务清单

本项目按以下任务逐步实施，每个任务完成后标记为完成状态。
中断后可从此文件继续。

## 任务列表

| # | 任务名 | 模块 | 状态 | 依赖 |
|---|--------|------|------|------|
| 1 | 还原前端样式，恢复原有聊天界面 | 前端修复 | completed | 无
| 2 | 新增 AgentKnowledgeBase 关联模型 | 后端模型 | completed | 无
| 3 | 新增 SystemSetting 模型 | 后端模型 | completed | 无
| 4 | 新增用户管理模型扩展 (role/enabled) | 后端模型 | completed | 无
| 5 | 新增知识库相关 Pydantic Schema | 后端 Schema | completed | 无
| 6 | 新增用户管理 Schema | 后端 Schema | completed | 无
| 7 | 新增系统设置 Schema | 后端 Schema | completed | 无
| 8 | 更新 Agent Schema 支持绑定 KB/MCP/Skill | 后端 Schema | completed | 5,2
| 9 | 实现知识库服务层 (文件解析/分块/向量化/检索) | 后端服务 | completed | 无
| 10 | 实现用户管理服务层 | 后端服务 | completed | 无
| 11 | 实现系统设置服务层 | 后端服务 | completed | 无
| 12 | 新增 Agent 知识库检索工具 | 后端工具 | completed | 9
| 13 | 更新 Agent 编排层集成知识库工具 | 后端 Agent | completed | 12
| 14 | 新增知识库 REST API 路由 | 后端 API | completed | 5,9
| 15 | 新增用户管理 REST API 路由 | 后端 API | completed | 6,10
| 16 | 新增系统设置 REST API 路由 | 后端 API | completed | 7,11
| 17 | 更新 Agent API 支持绑定 KB/MCP/Skill | 后端 API | completed | 8,14
| 18 | 前端新增知识库管理页面 | 前端 | completed | 1
| 19 | 前端新增用户管理页面 | 前端 | completed | 1
| 20 | 前端新增系统设置页面 | 前端 | completed | 1
| 21 | 前端 Agent 页面增加知识库绑定 UI | 前端 | completed | 18
| 22 | 前端 Agent 详情页增加对话测试区域 | 前端 | completed | 21
| 23 | 更新系统提示词 | 后端配置 | completed | 12
| 24 | 更新 requirements.txt | 依赖 | completed | 无
| 25 | 更新 README 文档 | 文档 | completed | 无
| 26 | 后端启动验证 | 验证 | completed | 全部后端
| 27 | 前端构建验证 | 验证 | completed | 全部前端
| 28 | 端到端测试 (上传→处理→检索→Agent对话) | 验证 | completed | 26,27
| 29 | 样式微调 & 最终检查 | 优化 | completed | 27

## 使用说明

1. 每个任务完成后，将状态从 pending 改为 in_progress 再改为 completed
2. 中断时记录当前进行中的任务
3. 恢复时从 in_progress 的任务继续
4. 依赖列表示该任务需要先完成的前置任务




