# term-debug v2 设计：agent 驱动/调试交互式终端的工具

日期：2026-10-05。状态：设计经四节逐一确认定稿。
证据基础：~/term_research/ 五份研究报告（屏幕模型 / tmux 机制 / 同步语义 / TUI 渲染与先行者 / 非视觉理解层），全部结论有一手实验输出或源码行号背书。

## 1. 问题与目标

Agent 需要驱动/调试交互式终端程序（bash、nano/vim/dialog 等全屏 TUI、自写 REPL、
ink/bubbletea 类动画 TUI 如 codebuddy CLI、ssh 远端、嵌套 tmux）。
v1 的单一代价：只有"regex 轮询 capture-pane"，真实运行中两次失败
（`'your name: '` 行尾空格被裁、`$ ` 提示符无尾随空格），且无法回答
"命令结束了吗/退出码多少/程序崩溃了吗"。

调试对象（全部必须支持好，架构预留扩展）：shell 命令、全屏 TUI、交互式 REPL、
现代动画 TUI、未来未知 TUI（以模块化扩展接入）。

## 2. 架构：Service + Client

```
agent ──▶ term-debug CLI（client，无状态短进程，零常驻内存）
              │
              ▼
        tmux server（service：PTY/会话/窗口真源）
              │
              ▼
        pane 里的目标程序
```

- 会话定位符 = **(socket, session, window, pane) 四元组**，`-L socket` 全命令透传。
  嵌套 tmux 实测可行：内层跑具名 socket（`TMUX= tmux -L inner new-session -d`），
  外层 client 直接 `tmux -L inner send-keys/capture-pane`（NESTED_OK_23 实验）。
- pane 定位用 **pane_id `%N`**（index 会重排）；显式 `-x/-y`（detached 默认 80x24）。
- 零驻留：state.json（磁盘）+ pipe-pane 直写落盘；不做内存优化项
  （client 无仿真器，tmux 开销即本职；多开开销可接受，按"收益太低就别管"关闭）。
- 模块：core（会话/send/capture）· wait 引擎（可插拔条件）· profiles
  （每类目标的参数包+推荐等待链，非新代码路径）· recorder（v2 落盘）·
  观察层（text/image 双通道平级）· 错误分类。

## 3. wait 引擎（四原语，AND 组合，强制 confidence 标注）

`wait -n TGT <条件…> [--timeout 30]` → 单行 JSON：
`{verdict, confidence, conditions, evidence}`。超时绝不杀进程，返回证据快照。
EOF（pane 死亡）是一切等待的提前终止条件。

| 原语 | 判定 | confidence |
|------|------|-----------|
| `--cmd-done [--expect-code N]` | raw 流自"上次 send 偏移"扫 OSC 133；A/B/C/D 状态机（D 仅在 C 后=完成；B 后无 C=aborted）；BEL/ESC\ 双兼容。注入按 VSCode 模板（PROMPT_COMMAND 首条取 $?） | fact |
| `--exit [--expect-code N]` | remain-on-exit + `pane_dead`/`pane_dead_status`；信号死亡读 `pane_dead_signal` | fact |
| `--until REGEX` | 屏幕正则（DOTALL 跨行、行尾空格两侧 rstrip 自愈）、`--scrollback N` 扩历史；红线：回显假阳性须锚定输出标记 | inference |
| `--quiet-ms N` | 动画免疫双采样：间隔 ≥N ms 两次 `(屏文本哈希+cursor_x/y+alternate_on+history_size)` 完全一致；CSI 2026 未闭合强制不稳定 | heuristic |

expect-code 不符 = 立即失败（非等超时）。`--timeout 0` 显式无限。

## 4. 观察层：text 与 image 双通道平级

- **text**：L1 状态头（`display-message` cursor_x/y、alternate_on、pane_in_mode、
  history_size 一次调用）→ L2 cell 网格 JSON + 属性 run 视图（run 级压缩控 token）
  → L3 语义标注 `[title][status][shortcut][selected][input]`（启发式，探针确认升级 confirmed）。
- **image**：`screenshot --format png|jpg`（字符网格+配色渲染为图片，参考 agg/termshot）。
  两通道平级，agent 按场景自选、可交替；不硬编码主备。
- 非视觉实证：SGR run 四通道（reverse/bold/fg/bg——dialog 用颜色不用 reverse）可程序化
  定位 TUI 选中项；探针法分两类（光标即选中 vs 光标钉死靠高亮 diff）；
  保真度 ≥ OS a11y API（iTerm2/WT 均丢属性）。
- 屏幕真源 = capture-pane（tmux 内部即 libvterm 级仿真器；pyte 实测无 alt-screen，
  只可作旁路）。capture-pane -e 是重合成序列，协议级字节一律走 pipe-pane。

## 5. 数据流与状态

`~/.cache/term-debug/<session>/`：raw.log（asciicast v2：o=原始流/i=注入/r=resize/m=同步点，
增量 crash-safe，未知事件码跳过）· state.json（socket、pane_id、width/height、
shell_integration、last_send_offset——**字节偏移而非时间戳**，原子写）·
trace.jsonl（人类可读投影，可随时重建，真理只在 raw.log+state.json）。
send 内部强制文本/键名分离（`-l`+键名混发 = 静默失败的实证坑）；需要 SIGQUIT 用 `-H 1c`。

## 6. 错误分类（JSON：code/message/hint/evidence）

`session-missing` `socket-unreachable` `pane-dead` `pane-dead-by-signal`
`no-shell-integration` `expect-code-mismatch` `timeout`(evidence=末屏+光标+条件状态)
`mouse-not-enabled`(检测自 \e[?1000/1006h) `tty-echo-broken`(回显缺失，建议 fix-tty)。

## 7. 输入原语

文本/组合键（send）、`click X Y`（SGR 鼠标序列 `\e[<b;x;yM/m` 经 -H 注入，
先检测应用已开鼠标上报）、光标移动（键序/C-a/C-e）、`fix-tty`（stty sane）。

## 8. 开发与验收方法论

- **e2e-first**：每个原语先写真实 E2E 场景（红）→ 实现（绿）→ 场景沉淀回归；
  场景少而真（真实 tmux/nano/bun/python，断言屏幕/退出码/trace），禁 mock。
- **启发式盲测协议**：我先实现 screenshot 通道并用图调试；然后给 subagent
  "试用者/志愿者体验者"人格 + 功能子集（屏蔽截图，仅启发式）完成定位/操作任务；
  以任务完成度 + 运行轨迹优化启发式，直到盲测接近我看图的水平。
- **第三方验收**：全新 subagent 只拿 CLI+skill，人格同上，**保留吐槽输出格式/易用性的权利**，
  吐槽记入《易用性反馈清单》驱动迭代。
- 验收硬指标：E2E 全绿+证据；实战调试任务（todo.js 双 bug）；
  边界全覆盖（行尾空格/ECHO 破坏/长行/CJK/pane 死亡/会话丢失/嵌套 tmux/多开干扰）；
  codebuddy 实战（启动→探索不发消息→切模型 hy3 非 hy3-x→对话→ESC 中断→双击 ESC 恢复）。

## 9. 参考实现与先行者定位

pyte(旁路/DebugScreen 日志) · avt & charmbracelet/x/vt(结构范式) · asciinema v2(格式)
· VSCode shell-integration(注入模板) · teatest(条件轮询范式) · ttyd(PTY 归 server)
· bnomei/tmux-mcp(命令状态机+侧信道) · tmux-bridge(read-before-act)。
先行者共同缺口=无稳定/就绪原语、无属性级语义导出——本工具的定位点。
