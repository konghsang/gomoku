
你的观察非常敏锐！这两个问题都是典型的“异步网络事件与本地 UI 阻塞”导致的“竞态条件”（Race Condition）。

下面是为你准备好的 `Code_Review_Report_V5.md` 任务书。你可以直接把这段内容发给 Cline，它能从根本上把这两个深层逻辑 Bug 彻底修好：

---

### 请将以下内容保存为 `Code_Review_Report_V5.md` 并发给 Cline：

**Markdown**

```
# 五子棋项目 - 弹窗错乱与战绩统计逻辑深度修复

你好，Cline。在测试刚才新增的“双向确认重开局”功能时，我们发现了两个由**UI 阻塞与异步网络时序**引发的深层 Bug。请读取以下分析，并对 `gomoku.py` 进行彻底修复。

## 一、 Bug 分析 (Root Cause)

### 1. 弹窗顺序倒置（先收到邀请，拒绝后才提示对方获胜）
**原因**：当对方下出制胜一步时，本地接收到 `MOVE` 报文并在 `_apply_move` 中更新了棋盘。但先前的代码中，**远端落子不会立刻触发胜负弹窗**，而是要等对方发送 `RESULT` 报文。如果对方胜利后立刻点击“再来一局”，发出了 `REMATCH_REQ`，由于 Tkinter 异步事件队列的特性，本地弹出了“对方邀请你”的请求；拒绝后，才继续处理 `RESULT` 报文弹出“白方获胜”。

### 2. 战绩统计记反（记录成了“作为黑方/白方的战绩”，而不是玩家自身的战绩）
**原因**：这是极其隐蔽的阻塞 Bug。在 `_apply_move` 中，原来的代码是先执行 `_show_result_dialog`（这是一个会阻塞线程的 `askyesno` 弹窗），然后才执行 `_update_stats(color)` 和 `_handle_remote_game_end()`。
**致命后果**：当玩家胜利并看到胜负弹窗时，主线程被挂起。但在后台，网络监听线程并没有停止！对端发来的 `NEXTBLACK`（换边指令）被后台处理，**提前把玩家的 `self.my_color` 翻转了**。等玩家关掉弹窗，代码继续往下走执行 `_update_stats` 时，核对的已经是**翻转后的新颜色**，导致战绩全部算到了对方（或颜色）头上！

---

## 二、 修复指令 (Action Required)

请对 `gomoku.py` 进行以下修改：

### 步骤 1：引入网络队列暂停机制，防止弹窗堆叠
在 `GomokuApp.__init__` 中新增 `self._dialog_open = False`。
修改 `_process_network_queue`，如果有弹窗正在显示，则暂停处理网络消息：
```python
    def _process_network_queue(self) -> None:
        if getattr(self, '_dialog_open', False):
            self.root.after(100, self._process_network_queue)
            return

        while True:
            try:
                kind, payload = self.net_queue.get_nowait()
            except queue.Empty:
                break
            # ... 下面的分支处理保持不变 ...
```

### 步骤 2：调整 `_apply_move` 的执行顺序（核心修复）

务必确保 **状态更新** 先于 **UI 弹窗** 执行。并且让本地和远端的落子都在第一时间调用胜负弹窗。

修改 `_apply_move` 内部的两处判定（禁手判负 和 成五获胜）：

**Python**

```
        if not result.legal:
            self.game_over = True
            winner = "白方" if color == Stone.BLACK else "黑方"
            final_message = f"{result.message} {winner}获胜。"
            self.last_move = (x, y)
            self._record_move(x, y, color, False)
            self._set_status(final_message)
            self._redraw()
            self.canvas.update()
          
            # 【关键修改】：先更新战绩和状态，再弹窗
            winner_color = Stone.WHITE if color == Stone.BLACK else Stone.BLACK
            self._update_stats(winner_color)
            self._handle_remote_game_end()
            self._update_cursor()
          
            # 无论本地还是远程落子，都直接调用弹窗
            self._show_result_dialog(final_message)
            return False

        # ... 中间代码不变 ...

        if result.win:
            self.game_over = True
            self._set_status(result.message)
          
            # 【关键修改】：先更新战绩和状态，再弹窗
            self._update_stats(color)
            self._handle_remote_game_end()
            self._update_cursor()
          
            # 无论本地还是远程落子，都直接调用弹窗
            self._show_result_dialog(result.message)
            return True
```

*(注意：`_on_click` 里的平局判定也需要确保 `self._update_stats(None)` 在 `self._show_result_dialog` 之前，请顺手检查)*

### 步骤 3：改造弹窗函数，接管锁定标记

修改 `_show_result_dialog` 和 `REMATCH_REQ` 的网络处理，加入 `self._dialog_open` 锁：

**Python**

```
    def _show_result_dialog(self, message: str) -> None:
        self._dialog_open = True
        if self.mode == "remote" and self.networked:
            want_rematch = messagebox.askyesno("对局结束", f"{message}\n\n是否邀请对方开启下一局？")
            self._dialog_open = False
            if want_rematch:
                self._send_rematch_request()
            else:
                self._set_status("已取消下一局，等待对方邀请或自行重新开始。")
        else:
            messagebox.showinfo("对局结束", message)
            self._dialog_open = False
```

在 `_handle_net_message` 处理 `REMATCH_REQ` 的地方：

**Python**

```
        if message.startswith("REMATCH_REQ|"):
            # ... 前面的 session_id 校验和 waiting_rematch_reply 判断不变 ...

            self._dialog_open = True
            msg = "对方邀请您开启下一局，是否同意？" if self.game_over else "对方请求重新开始当前对局，是否同意？\n(当前进度将作废)"
            agree = messagebox.askyesno("对局请求", msg)
            self._dialog_open = False
          
            if agree:
                self._send_net(f"REMATCH_ACK|{self.session_id}|ACCEPT")
                self._execute_rematch()
            else:
                self._send_net(f"REMATCH_ACK|{self.session_id}|REJECT")
                self._set_status("已拒绝对方的重新对局请求。")
            return
```

### 步骤 4：废除冗余的 RESULT 报文逻辑

因为现在 `_apply_move` 直接接管了所有的胜负弹窗，我们不需要再依赖对方发来的 `RESULT` 报文来弹窗了。

在 `_handle_net_message` 中：

**Python**

```
        if message.startswith("RESULT|"):
            # 【修改】已由本地 _apply_move 同步处理胜负弹窗，直接 return 忽略该报文
            return
```

## 总结任务

Cline，请严格按照上述 4 个步骤进行逻辑重构。这不仅能修复战绩被“后台偷偷换边”篡改的 Bug，还能通过“弹窗排他锁”保证玩家必定先看到“对局结束”，然后才会处理后续的任何重开邀请请求。完成后请简要总结。
