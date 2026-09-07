# Hybrid Codex

**简体中文** | [English](README.en.md)

**原生 Codex 负责思考、实现与验收；ChatGPT Web 负责有边界的只读并行调查。**

原生 Codex 是主模型，ChatGPT Web 通过 MCP 提供只读 Worker。
本仓库提供可复用的用户级 skill、固定版本的 specialist 后端，以及适配已有 launcher
的兼容补丁，无需 LazyCodex。

```text
Native Codex Parent → native Codex backend
├─ Native tools: search, shell, edits, tests
├─ Native subagents: planning, implementation, verification
└─ Explicit chatgpt-web MCP
   → Existing Codex Web GPT launcher
   → ChatGPT Web workers (up to 5)
```

## 能做什么

- `chatgpt_web_turn`：一个聚焦的阅读/分析任务。
- `chatgpt_web_batch`：最多五个独立任务；准备和发送阶段排队，生成阶段可重叠。
- `chatgpt_web_status`：查看当前 MCP runtime 的槽位、任务与队列。
- `chatgpt_web_cancel`：取消本任务拥有的 job。
- `$web-workers`：指导 Parent 先本地搜索，再编译上下文、委派、回收并复核。

适合代码阅读、模块总结、依赖梳理、调用关系、日志分析、测试失败分类和边界枚举。
需求解释、架构、关键取舍、仓库修改、测试执行及最终判断由 Parent 保留。

## 前提与边界

本项目是**已有安装的集成层**，不是 ChatGPT 登录器或浏览器 daemon 安装器。

- Python 3.11+、Git、Bun。
- 已安装并登录的 [codex-chatgpt-web](https://github.com/miuuyy/codex-chatgpt-web) launcher。
- 已验证的组合：Windows、launcher/runtime 4.0.8、descriptor v2、Bun 1.4.0。
  specialist 上游声明 Bun 1.3.14；其他版本/平台请重新验证，不保证即插即用。
- Parent 应使用原生 provider。此项目**不设置或修改 `openai_base_url`**，不创建第二套 daemon。
- Web Worker 只看到 Parent 发出的材料，没有本地工具。它不是 OS 级隔离沙箱。
- 调用会把你选择的文本发送到登录的 ChatGPT 账户；不要发送凭据、完整仓库或无关对话。

如果根 `openai_base_url` 仍指向旧本地 bridge，先按[迁移说明](docs/architecture.md)
检查并断开 Parent 路由。不要为修复 Worker 故障恢复整个 Parent bridge。

## 安装

```sh
git clone --recurse-submodules https://github.com/LilPolaris/hybrid-codex.git
cd hybrid-codex
```

**已有可用的 `chatgpt-web` MCP，只想在所有项目使用 skill：**

```sh
python scripts/setup.py skill
```

skill 安装到 `$CODEX_HOME/skills/web-workers`，未设置 CODEX_HOME 时是
`~/.codex/skills/web-workers`。已有版本会先备份；重复安装相同内容不会重复备份。
不修改 Parent 或 MCP 配置。

**已有兼容 launcher 和登录，但尚未接入 specialist MCP：**

```sh
python scripts/setup.py backend
python scripts/setup.py skill
python scripts/setup.py doctor
```

`backend` 校验固定上游 commit、应用本仓库补丁、安装锁定依赖，再追加 MCP 表。
配置写入前备份；已有不同的同名 MCP 时直接报错，不覆盖。它不执行上游 setup、
serve、install-codex，也不修改登录或 launcher 配置。

Bun 不在 PATH 时会复用已有 launcher config 的 runtimeCommand；也可传
`--bun /absolute/path/to/bun`。自定义安装目录使用现有的
`CURSOR_CHATGPT_WEB_HOME` 或 `CODEX_CHATGPT_WEB_HOME`。

安装后新开 Codex 任务；若工具/skill 清单仍旧，完整重启 Codex。

## 使用

在任意业务项目或文件任务中输入：

> $web-workers 用三个只读 Worker 分别调查登录中间件、前端登录流程和测试覆盖。
> 你先筛选材料，回收并复核关键结论，再决定如何修改。

单个文件也可以：

> $web-workers 阅读我指定文件的相关片段，总结职责与边界情况，由你核验。

Parent 应先搜索并读取材料，然后编译：

```text
TASK / GOAL / SCOPE / RELEVANT CODE
CONSTRAINTS / QUESTIONS / OUTPUT FORMAT
```

主模型在日常任务中自主识别边界清楚、易验收的阅读、分析和草稿杂活，无需每次点名 skill。
默认顺序：网页最高可用档位 → 原生 `gpt-5.6-luna` / `max` → 主模型兜底。
网页先查 status，按 `pro → extra-high → high → medium → instant` 选择首个可用档位；
这里的“最高”指思考档位，不代表剩余使用额度。网页 `luna` 不等于原生 Luna max。
失败时简短说明降级原因；只对已诊断的临时或输入问题重试一次，避免反复空转。
这是 skill 的分派策略，依赖宿主加载 skill 和提供对应工具，不是后台强制路由器。
2–5 个独立调查优先 batch，简单 grep/文件搜索仍本地完成。
重要结论遵循：Worker claim → Parent 查看代码或运行结果 → 验证 → 用于决策。

### 每次委派的数字与故障冷却

skill 在委派前记录主模型工作量的估算基线，结束后直接在对话中显示：

> 委派 log-review | web/high → luna/max | 24.6s | 主模型净节省估算 −200…+1,000 tokens

这是展示格式示例。区间会扣除准备、回读、验证和失败尝试的额外成本；负数表示
可能更费 token。无法可靠估计时显示“待估算”，不会把 Worker 用量当作节省量。
它不代表真实账单、剩余额度或全账户节省，Luna 也会消耗原生账户用量。

同一任务会记住故障：登录失败冷却 30 分钟、额度耗尽 60 分钟、工具不可用 10 分钟、
临时故障 60 秒，期间其他子任务跳过对应模型。状态保存在本地 SQLite，任务恢复后
仍有效；不同任务互不影响。运行中或未确认取消的工作会阻止重复分派。

不需要打开本地报告。安装器会一并安装记账脚本；数据默认放在
`$CODEX_HOME/worker-metrics/ledger.sqlite`，只记录标识、数字与简短状态。
详细流程见 [记账说明](.agents/skills/web-workers/references/meter.md)。

## 验证

```sh
python -m unittest discover -s tests -p "test_*.py"
python scripts/setup.py doctor
bun scripts/smoke.ts status
```

后两项只验证静态配置/MCP连接，**不证明网页生成成功**。下面命令会实际请求 ChatGPT：

```sh
bun scripts/smoke.ts single
bun scripts/smoke.ts batch
```

脚本记录写入被忽略的 `reports/`。脚本验证后，还应在正常 Codex 任务里通过
`$web-workers` 直接调用工具，确认会话加载和 Parent 复核流程。

本机验收记录的可公开摘要：原生 Parent/high、原生 subagent、重启后四个 MCP
工具、真实单 Worker 和三 Worker 均通过；一次三任务生成窗口共同重叠 11.923 秒。
这是一次实测结果，不是性能保证。私有配置、登录、会话ID、完整日志没有随仓库发布。

自动降级与冷却有独立测试，覆盖网页成功、Luna 接手、主模型兜底、冷却恢复、
重复记录、运行中锁定和负节省计算。真实工具验收与故障注入结果须分别报告，
故障注入不代表账号曾发生真实故障。
本轮真实调用、取消与降级的验收范围见[验收记录](docs/worker-acceptance.md)。

## 源码与维护

- `.agents/skills/web-workers/`：可发布、可安装的 skill 源码。
- `scripts/setup.py`：用户级 skill 与现有 launcher 的 MCP 接入。
- `scripts/smoke.ts`：独立 MCP 连接和可选真实 smoke。
- `vendor/cursor-chatgpt-web/`：固定上游 Git 子模块。
- `patches/cursor-chatgpt-web.patch`：v2 launcher/helper 兼容、准备门控、只读 MCP 策略。

子模块按设计保留工作区补丁，父仓库忽略其 dirty 状态。用
`git -C vendor/cursor-chatgpt-web diff` 检查补丁；不要直接更新子模块到 latest。
本项目安装器遇到不同 revision 会拒绝套用补丁。当前上游全仓库 typecheck 有已知
错误，不宣称全部测试通过；参见[兼容性说明](docs/compatibility.md)。

## 许可证与致谢

MIT。此项目基于 [Rakeem-C/cursor-chatgpt-web](https://github.com/Rakeem-C/cursor-chatgpt-web)
的 specialist MCP 和 [miuuyy/codex-chatgpt-web](https://github.com/miuuyy/codex-chatgpt-web)
的浏览器/launcher 能力；相关版权见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
这是社区集成项目，与 OpenAI 没有官方隶属关系。
