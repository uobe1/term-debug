# term-debug v2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 把 term-debug 从"regex 轮询原型"升级为证据驱动的交互式终端调试 CLI+skill（Service=tmux / Client=CLI / 状态落盘）。

**Architecture:** 设计定稿见 `docs/plans/2026-10-05-term-debug-v2-design.md`（同分支已提交）。要点：会话定位四元组 (socket,session,window,pane)；wait 四原语带 fact/inference/heuristic 标注；text(SGR网格)+image(png/jpg) 双通道平级观察；asciicast v2 原始流落盘；结构化错误分类。

**Tech Stack:** Python 3.14 stdlib 为主；Pillow（仅 screenshot 用，缺失时结构化报错）；tmux 3.7c（外部唯一依赖）。

**e2e-first 纪律（每个任务相同循环）：** 写真实 E2E 场景（红）→ 跑它确认失败 → 最小实现（绿）→ 全量场景回归 → commit。E2E 场景=只通过 CLI 驱动真实程序的 bash 脚本（`set -euo pipefail`，断言失败时打印证据，退出非零）。禁止 mock、禁止绕过 CLI 直接操作目标文件。

**布局约定：** 包 `termdebug/`（避免与根入口 `term_debug.py` 重名），根文件 `term_debug.py` 仅作 shebang shim。测试 `tests/e2e/NN_name.sh` + `tests/unit/test_parsers.py`（纯 assert，无 pytest 依赖）。所有命令默认在 worktree 根执行：`/data/data/com.termux/files/home/agent-i/.worktrees/term-debug-v2`。

---

### Task 0: 包骨架 + 错误分类 + CLI 骨架

**Files:**
- Create: `termdebug/__init__.py`、`termdebug/errors.py`、`termdebug/cli.py`
- Modify: `term_debug.py`（改为 shim：`#!/usr/bin/env python3; import sys; from termdebug.cli import main; sys.exit(main())`）
- Test: `tests/unit/test_errors.py`

**Step 1:** `errors.py` 定义 `TDError(code, message, hint=None, evidence=None)`，`to_json()` 输出 `{"error":{"code","message","hint","evidence"}}`；码表常量（design 第6节 9 个 code）。`test_errors.py` 断言 JSON 形状。
**Step 2:** `python3 tests/unit/test_errors.py` → 先红（模块不存在）。
**Step 3:** 实现至绿。`cli.py`：argparse 骨架，子命令 start/stop/send/screen/wait/sessions/trace/fix-tty/screenshot/mouse-detect，未实现子命令抛 `TDError("not-implemented")`。
**Step 4:** `python3 term_debug.py --help` 退出 0。
**Step 5:** `git add -A && git commit -m "feat(v2): package skeleton + error taxonomy"`

### Task 1: 定位四元组 + v2 录制器 + start/stop

**Files:**
- Create: `termdebug/tmuxio.py`（`parse_target("sock:sess:win.pane"|"sess")` → `(socket|None, sess, win|None, pane|None)`；`tmux(*args, socket=None)` 组装 `-L`；`capture(target, flags)`、`meta(target)` 用 `display-message -p` 输出 cursor_x/cursor_y/alternate_on/pane_in_mode/history_size/pane_dead/pane_dead_status/pane_dead_signal）、`termdebug/records.py`（`V2Writer`: header+append(code,data)；`state.json` 原子写 tmp+rename；目录 `~/.cache/term-debug/<sess>/`）
- Test: `tests/unit/test_locators.py`、`tests/e2e/01_start_stop.sh`

**Step 1:** 写 `01_start_stop.sh`：`term_debug.py start -n s01 --cmd bash` → 断言 `tmux has-session`、raw.log 首行 JSON 含 `"version":2` 且 width/height 与 `--width/--height` 一致、state.json 含 `"pane_id":"%` 前缀与 `shell_integration` 字段（本任务先 false）；`stop` 后会话消失。失败打证据。
**Step 2:** 跑 → 红（无实现）。
**Step 3:** 实现 start：`tmux new-session -d -s -x -y "bash"` → `set-option remain-on-exit on` → `format -F '#{pane_id}'` 存 %N → V2Writer 写 header（env 只收 SHELL/TERM）→ state.json。stop：kill-session + v2 收尾事件。
**Step 4:** 绿；`tests/unit/test_locators.py` 覆盖 `s` / `s:1` / `s:1.0` / `sock:s:1.0` 四种形态。
**Step 5:** commit `feat(v2): four-tuple locator + asciicast v2 recorder + start/stop`

### Task 2: send（文本/键分离 + i 事件 + 偏移）

**Files:** Modify `termdebug/cli.py`、Create `termdebug/input.py`
**Test:** `tests/e2e/02_send_roundtrip.sh`

**Step 1:** 写场景：start → `send --type "echo TD2_OK"` → 单独 `send --key Enter` → `wait --until 'TD2_OK'` → 断言退出 0 且屏幕含 TD2_OK；断言 raw.log 出现 `"i"` 事件且记录了 Enter；断言 state.json 的 `last_send_offset` 在两次 send 后递增。
**Step 2:** 红。
**Step 3:** 实现：send 内部**永远**把 `--type` 与 `--key` 拆成独立 `tmux send-keys` 调用（`-l` 文本；键名/`-H` 十六进制单独调用）；send 前取 raw.log 尺寸记偏移。
**Step 4:** 绿 + 回归 01。
**Step 5:** commit `feat(v2): split send + input events + send offset`

### Task 3: screen text 通道（meta/diff/grid/runs/grep/element-at）

**Files:** Create `termdebug/screen.py`（SGR 解析状态机：按字符流处理 `\e[<n>m`，跨行延续；输出 cell 网格 `{char,fg,bg,attrs,x,y}`、属性 run 列表）
**Test:** `tests/e2e/03_screen_channels.sh`、`tests/unit/test_sgr.py`（用研究期 `sgr_grid.py` 的样例字节）

**Step 1:** 场景：start → `printf '\033[31mRED_TEXT\033[0m      \n'`（尾随空格+颜色）→
  `screen --meta` 含 `"cursor_x"`/`"alternate_on":false`；
  `screen --keep-trailing`（-N）行尾空格保留；`--join`（-J）对 200 字符长行还原逻辑行；
  `screen --scrollback 50`；`screen --grid` 输出含 `"fg":"red"` 的 cell；
  `screen --runs` 输出 `[{"fg":"red","text":"RED_TEXT"}]` 形态；
  `screen --grep --fg red` 命中该行；`screen --element-at <x> <y>` 返回该 cell。
**Step 2:** 红。**Step 3:** 实现（SGR 解析参考研究产物 `term_research/sgr_grid.py`，重写为库函数）。**Step 4:** 绿 + 回归。**Step 5:** commit `feat(v2): text observation channels (meta/grid/runs/grep/element-at)`

### Task 4: wait 引擎骨架（verdict JSON + confidence + timeout 证据 + --until 自愈/--scrollback）

**Files:** Create `termdebug/waiting.py`（`Condition` 抽象：`evaluate(ctx)->bool`+`label`；`Verdict` 组装；AND 组合）
**Test:** `tests/e2e/04_wait_regex.sh`、`tests/unit/test_verdict.py`

**Step 1:** 场景：`wait --until 'TD4: '`（**带尾随空格的模式**，对 rstrip 后屏幕必须命中——自愈红线）退出 0 且 JSON `confidence:"inference"`；`wait --until 'NEVER_XYZ' --timeout 1` 退出非 0，JSON 含 `error.code:"timeout"` 与 `evidence.screen` 非空、`evidence.cursor` 存在；`--scrollback 200` 能命中已滚出屏幕的行（先 `seq 1 300` 制造历史）。
**Step 2:** 红。**Step 3:** 实现 regex 条件（DOTALL、两侧 rstrip 重试）+ timeout 证据路径。**Step 4:** 绿。**Step 5:** commit `feat(v2): wait engine core + regex self-heal + timeout evidence`

### Task 5: OSC 133 状态机 + 注入 + `--cmd-done`

**Files:** Create `termdebug/osc133.py`（A/B/C/D 状态机：输入字节流+起始偏移，输出完成/中止事件与退出码；BEL 0x07 与 ESC\ 双结尾；按转义序列边界跳过其它序列）、`termdebug/rcfile.py`（bash 注入模板：PROMPT_COMMAND **首条**取 `$?`，发 `\033]133;D;%s\007` + `\033]133;A\007`；PS1 用 `\[\]` 包裹）
**Test:** `tests/unit/test_osc133.py`（直接喂研究报告里的真实字节样本：D;0/D;1/D;42 + 2004h 混杂流）、`tests/e2e/05_cmd_done.sh`

**Step 1:** 场景：start（state.json `shell_integration:true`）→ 依次 `send true/Enter`、`wait --cmd-done --expect-code 0`；`false` → expect 1；`sh -c 'exit 42'` → expect 42；`wait --cmd-done --expect-code 5` 对实际 7 → **立即失败**（耗时 < 2s，非 30s 超时）`error.code:"expect-code-mismatch"`；JSON `confidence:"fact"`。
**Step 2:** 红。**Step 3:** 实现；start 时改用 `bash --rcfile <cachedir>/bashrc -i`；`--cmd` 非 bash 时不注入（state 标 false）。**Step 4:** 绿。**Step 5:** commit `feat(v2): OSC133 injection + cmd-done (fact)`

### Task 6: `--exit` + 信号死亡

**Test:** `tests/e2e/06_exit_and_signals.sh`
**Step 1:** 场景：`sh -c 'exit 7'` → `wait --exit --expect-code 7` fact 命中；`kill -9 $$` → verdict `pane-dead-by-signal`（evidence 含 `KILL`）+ hint 提供 respawn 指引；EOF 提前终止：`wait --cmd-done` 期间程序崩溃 → 立即返回 pane-dead 而非等满 30s（断言耗时 < 5s）。
**Step 2:** 红 → **Step 3** 实现（pane_dead_status/pane_dead_signal，Task 1 已留 meta）→ **Step 4** 绿 → **Step 5** commit `feat(v2): exit/signal conditions + EOF early-termination`

### Task 7: `--quiet-ms` 动画免疫双采样

**Test:** `tests/e2e/07_quiet.sh`
**Step 1:** 场景 A（周期输出）：后台起 `for i in $(seq 8); do echo tick$i; sleep 0.3; done` → `wait --quiet-ms 1000 --timeout 10` 必须**在最后一个 tick 之后**才命中（用 raw.log 中 tick8 的 v2 时间戳 vs wait 命中的 m 事件时间戳断言顺序）；场景 B（动画模拟）：`python3 tests/fixtures/spinner.py`（每 150ms 原地重绘帧，跑 3s 后停）→ `wait --quiet-ms 400 --timeout 8` 命中时间 ≥ spinner 停止时刻；场景 C：输出中夹一次 `\033[?2026h`（不闭合）→ 800ms 内不判稳。
**Step 2:** 红 → **Step 3** 实现（双采样 (屏哈希+cursor_x/y+alternate_on+history_size)；采样间隔=max(N,250ms)；CSI2026 未闭合检测扫 raw 尾部）→ **Step 4** 绿 → **Step 5** commit `feat(v2): animation-immune quiet detection (heuristic)`

### Task 8: 鼠标（检测 + click）

**Files:** `input.py` 增 `mouse_encode(button,x,y,press)`（SGR: `\e[<0;x; yM/m`，坐标+1）与 `mouse_mode(raw_tail)` 检测 `\e[?1000h`/`\e[?1006h`
**Test:** `tests/e2e/08_mouse_click.sh` + `tests/fixtures/curses_mouse.py`（开启鼠标的 curses 程序：点击屏上某格打印 CLICKED:x,y）
**Step 1:** 场景：跑 fixtures 程序 → `mouse-detect` 报 enabled → `click 10 5` → 屏幕出现 CLICKED:9,4（0 基换算断言）；对照组：普通 bash 里 `click` → `error.code:"mouse-not-enabled"`。
**Step 2-5:** 红绿回归，commit `feat(v2): SGR mouse click + mode detection`

### Task 9: fix-tty 与 ECHO 破坏检测

**Test:** `tests/e2e/09_tty_echo.sh`
**Step 1:** 场景：pane 内 `stty -echo` → `send --type "echo hi"` 后 1s 内 raw.log 无回显字节 → `send` 的返回 JSON 附 `"warning":"tty-echo-broken"`（不报错，程序可能合法关 ECHO）→ `fix-tty` → `stty -a` 屏幕显示 `echo` → 再 send 回显正常无 warning。
**Step 2-5:** 红绿回归，commit `feat(v2): echo-broken detection + fix-tty`

### Task 10: screenshot（png/jpg）

**Files:** Create `termdebug/screenshot.py`（输入=屏文本+SGR 属性网格；Pillow 画等宽字符格：前景/背景色、reverse 取反、16/256 色映射 RGB；字体探测顺序 `/system/fonts/DroidSansMono*.ttf`、`/system/fonts/*.ttf` 含 mono 关键字、`$PREFIX/share/fonts`；PNG 与 JPG（quality=92））
**Test:** `tests/e2e/10_screenshot.sh`
**Step 1:** 场景：nano 打开文件 → `screenshot --format png -o /tmp/s.png` 与 `--format jpg -o /tmp/s.jpg` → 两文件存在、>5KB、PIL 能 open 且尺寸==(width*charw, height*lineh)；无 Pillow 环境（`PYTHONPATH=` 隔离模拟）→ `error.code:"pillow-missing"` 带 pip 安装 hint。
**Step 2-5:** 红绿回归，commit `feat(v2): screenshot png/jpg via Pillow`

### Task 11: sessions 列表 + 嵌套 socket 端到端

**Test:** `tests/e2e/11_nested_tmux.sh`
**Step 1:** 场景：start 外层 → pane 内 `TMUX= tmux -L inner new-session -d -s inner` → `sessions --socket inner` 列出内层 → `send -n "inner:inner" ...`、`wait/capture` 全链路对内层 pane 生效（复刻 NESTED_OK_23 实验）→ 多开互扰检查：同时存在 ≥2 会话时各自 wait 互不影响。
**Step 2-5:** 红绿回归，commit `feat(v2): multi-socket sessions + nested tmux e2e`

### Task 12: trace v2

**Files:** `cli.py` 的 trace 改为投影 raw.log：默认人类可读（i/o 摘要/m 同步点/错误事件），`--format json` 原样 NDJSON。
**Test:** `tests/e2e/12_trace.sh`（跑完 01-11 累积会话之一，断言 o/i/m 事件都在且时间戳单调）。
红绿回归，commit `feat(v2): trace as v2 projection`

### Task 13: SKILL.md 重写（v2）

**Files:** Modify `skills/debugging-interactive-terminals/SKILL.md`
**Step 1:** 按 writing-skills 规范重写：frontmatter 触发式 description；正文=核心原则（先等状态再行动、confidence 分级用法）+ 四原语速查 + **双通道选择指引**（属性/语义查询→text；空间布局/线框→screenshot）+ 坑清单（-l Enter、尾随空格、marker 不可信、spinner 与 quiet、C-\ 用 -H 1c）+ **防作弊红线**（禁用 Edit/Write 绕过 CLI；交付必附 raw.log/trace）+ 四标准场景（nano/REPL/todo.js 双 bug/codebuddy 实战）+ 试用者吐槽协议。
**Step 2:** 用 subagent 做一次检索演练：只给 skill，问"如何确认命令结束/退出码"，答案必须指向 `--cmd-done`。
**Step 3:** commit `docs(v2): skill rewrite for evidence-driven debugging`

### Task 14: 盲测协议 + 验收跑通

**Files:** Create `tests/blind/run_blind.sh`（协议文档化：TERM_DEBUG_DISABLE_IMAGE=1 环境开关——screenshot 在此开关下返回 `pillow-missing` 式结构化错误；提示词模板=试用者人格+吐槽权）
**Step 1:** 实现 `TERM_DEBUG_DISABLE_IMAGE` 检查（screenshot 入口）。
**Step 2:** 我（主 agent）亲自跑通三个真实任务：① nano 编辑+运行 python（v1 流程回归）；② todo.js 双 bug 复现与修复（bun，先调试后修码）；③ codebuddy 实战（启动→探索→切模型 hy3→对话→ESC 中断→双击 ESC 恢复）。
**Step 3:** 盲测：派 subagent（仅启发式）做 todo.js 修复，记录完成度+轨迹+吐槽 → 修启发式弱项。
**Step 4:** 第三方"志愿者体验者"全量验收（CLI+skill，黑盒）。
**Step 5:** 全量 E2E 绿 → `finishing-a-development-branch` 流程合并 main → push。

---

## 风险与预案
- Termux 无合适等宽 TTF → screenshot 任务先做字体探测实验（系统字体目录列举）再实现。
- codebuddy ink 应用 ESC/双击 ESC 语义未知 → Task 14 ③ 期间以 raw.log 事后分析按键回显与重绘节奏，必要时给 profiles 加 ink-app 预设（延长 quiet 采样间隔）。
- v1 的 `wait --until '[$#]\s*$'` 类场景由 Task 5 的 cmd-done 取代，skill 中标注弃用。
