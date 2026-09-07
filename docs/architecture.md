# Parent 与 Worker 是两条独立路径

Parent 使用原生 Codex 模型、原生工具和原生子 agent。Web 仅作为显式 MCP
worker：它不会接管主请求，不拥有文件读写工具，也不做最终决策。

## 已有旧 bridge 时

先检查用户 `config.toml`、更高优先级覆盖、进程连接及会话模型元数据。
配置名或模型名不能单独证明实际链路。旧 bridge 可能只是把原生模型转发到
官方 backend，但仍然位于 Parent 请求链上。

若需要移除该层，先备份 config.toml 与旧安装的 integration journal，再使用
**该安装自身支持的** `route disconnect`。不要卸载整个旧安装，也不要照搬别人的
固定 PID、版本路径或自动重启脚本。

4.0.8 的 disconnect 可能同时恢复它以前托管的 multi-agent 设置。检查 diff，
将需要保留的 native multi-agent 配置明确作为用户设置保留，并保持 chatgpt-web
MCP 表不变。旧 journal 可能因此报告“断开后用户更改”保护提示；不应修改历史
journal 来隐藏提示，也不应因此重新接通 Parent bridge。

重启后以新进程、真实 Parent 请求、实际 turn_context effort 和连接采样验证。
磁盘默认 high 不意味着一个已恢复的旧轮次立即变成 high。

## 限制与故障

- MCP task pool 的五槽上限是 runtime 实例内的；共享 launcher 还有五标签限制。
- 准备阶段门控是 helper 实例内的，不是全机器跨进程锁。
- `Promise.all` 的 batch 失败不自动取消所有其他任务；在同一 MCP runtime
  检查 status，再仅取消本任务拥有的 jobId。
- `allowedPaths` 或只读提示不能代替 OS 沙箱。这里通过不提供本地工具限制
  Web Worker，Parent 自己读取和筛选材料。
- Web UI、账号模式、登录状态、launcher 协议变化都可能破坏兼容性。失败应报告
  原因，不能用模拟结果、静默换模型或重新代理 Parent 掩盖。

不需要 LazyCodex 即可使用该架构。若以后接入其他编排器，只用项目规则/skill
选择适合委派的阅读任务，规划者、实现者、最终审查者继续保持原生。
