
这是一个为你准备的、可以直接交给 Cline 读取的 **完整版 Markdown 任务书** 。

这份文档将你之前的“逻辑规范自查”和刚刚发现的“联机 Bug 修复与网络优化”结合在了一起。你只需要将以下内容保存为 `Cline_Gomoku_Task.md`，然后让 Cline 读取并执行即可。

---

### 请将以下内容保存并提供给 Cline：

**Markdown**

```
# 五子棋项目 (Gomoku) 全量代码审查与 Bug 修复任务书

你好，Cline。本任务书包含了当前五子棋项目（`gomoku.py` 等文件）的核心修复指令与逻辑自查规范。请仔细阅读以下要求，直接对工作区中的代码进行修改，并在完成后提供修改总结。

## 优先级 1：修复核心 Bug（联机落子颜色反转与卡死）

### 问题描述
在远程联机模式下，当执黑方的玩家落子后，对面的客户端在相同位置显示的是白子，随后游戏流程卡死。

### 根本原因
在 `gomoku.py` 的 `_on_click` 方法中，代码先调用了 `self._apply_move(x, y, self.current_player)`。在 `_apply_move` 内部，成功落子后执行了状态切换：`self.current_player = Stone.WHITE if color == Stone.BLACK else Stone.BLACK`。
随后 `_on_click` 调用 `self._send_move_if_needed(x, y)`。但此时 `self.current_player` 已经变成了下一个玩家的颜色！因此，`_send_move_if_needed` 内部使用 `self.current_player` 推断颜色时发出了错误的报文，导致两端状态机脱节（Desync）并卡死。

### 修复指令
请对 `gomoku.py` 进行以下修改：
1. **修改 `_send_move_if_needed` 的签名与逻辑**：
   将其改为接收当前落子的颜色参数：`def _send_move_if_needed(self, x: int, y: int, color: int) -> None:`。
   内部逻辑改为：`color_str = "BLACK" if color == Stone.BLACK else "WHITE"`。
2. **修改 `_on_click` 中的调用方式**：
   在调用 `_apply_move` 之前，先将当前颜色保存到局部变量中，然后再传递给网络发送函数。
   ```python
   # 预期修改模式：
   current_color = self.current_player
   if self._apply_move(x, y, current_color):
       self._send_move_if_needed(x, y, current_color)
```

---

## 优先级 2：网络模块健壮性优化

请在修改 Bug 的同时，对 `gomoku.py` 的网络模块进行以下两项加固^^：

1. **防止 TCP 粘包导致的 OOM** ：
   在 `_start_receiver_thread` 方法中，`buffer += data.decode("utf-8")` 之后，加入长度限制机制（例如 `if len(buffer) > 10240: buffer = ""` 并在内部触发 `DISCONNECTED` 队列消息），防止极端情况或恶意数据导致内存溢出^^。
2. **游戏中断线弹窗提示** ：
   在 `_process_network_queue` 方法处理 `DISCONNECTED` 事件时，除了更新状态栏 `_set_status` 外，如果游戏仍在进行中，请使用 `messagebox.showwarning` 或 `messagebox.showinfo` 弹窗明确告知玩家“连接已断开”^^。注意不要阻塞主事件循环。

---

## 优先级 3：禁手与胜负逻辑静态审查（Renju 规则）

在修复完上述问题后，请基于以下规则对 `gomoku.py` 中的判定逻辑（如 `check_black_move` 等）进行一次静态代码审查^^，确保没有遗漏的边缘情况：

1. **基础胜负（五连）** ：任意方向恰好 5 个同色棋子即获胜[cite: 1]。
2. **白方特权** ：白方无禁手，连成 5 子或 ≥6 子（长连）均获胜[cite: 1]。
3. **黑方长连禁手 (Overline)** ：黑方形成连续的 6 个或以上黑子，判负[cite: 1]。
4. **黑方四四禁手 (Four-Four)** ：黑方一子落下，同时形成两个或以上的“四”（包含活四和冲四）。**注意：** 落子点必须在每一个“四”中[cite: 1]。
5. **黑方三三禁手 (Three-Three)** ：黑方一子落下，同时形成两个或以上的“活三”。**注意：** 活三必须保证两端紧邻位为空，且至少一端再往外一格也为空（具备形成活四的潜力）[cite: 1]。
6. **五绝对优先原则** ：如果黑方落子同时形成“五连”和“禁手”（例如五连+长连，或五连+四四），则 **禁手失效** ，直接判黑方五连获胜[cite: 1]。

---

## 给 Cline 的执行清单

* [ ] 步骤 1：修复 `_on_click` 和 `_send_move_if_needed` 的时序 Bug，解决联机颜色反转问题[cite: 1]。
* [ ] 步骤 2：在接收线程中加入 `buffer` 长度限制，防止 OOM[cite: 1]。
* [ ] 步骤 3：在断线处理逻辑中加入 UI 弹窗提示[cite: 1]。
* [ ] 步骤 4：通读 `check_black_move` 及相关辅助函数，核对是否完全符合上述禁手规则。如果有隐患，请一并修复[cite: 1]。
* [ ] 步骤 5：完成所有修改后，向用户输出一份简明的修改总结报告。
