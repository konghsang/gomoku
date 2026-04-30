
这是一个非常精准的测试反馈！第二局出现异常的原因在于 **联机状态下的“对局结算时序”与“黑白轮换”逻辑产生了冲突** ，导致第二局双方的颜色状态没有正确同步。

我为你准备了一份新的 `Code_Review_Report_V2.md`，专门针对这个“第二局异常（双重触发导致的黑白不轮换）” Bug 进行修复，并加入了你要求的“对局次数、当前执黑执白、胜负记录”等 UI 显示功能。

你可以直接将以下内容保存为 `Code_Review_Report_V2.md`，然后交给 Cline 去执行：

---

### 请将以下内容保存为 `Code_Review_Report_V2.md` 提供给 Cline：

**Markdown**

```
# 五子棋项目 - 第二局联机异常修复与战绩 UI 升级任务书

你好，Cline。经过进一步的联机测试，我们发现第一局对局正常，但在第一局结束后进入第二局时，游戏状态出现了异常（执黑执白没有正确轮换或两端状态脱节）。
同时，为了避免后续对局中玩家产生混乱，我们需要在 UI 上加入清晰的战绩面板和执子提醒。

请读取以下分析，并对 `gomoku.py` 进行修改。

## 一、 核心 Bug 修复：第二局换边异常

### 1. Root Cause 分析
在游戏结束时，主机会调用 `self._handle_remote_game_end()` 来翻转 `self.remote_black_is_host`，并向客户端发送 `NEXTBLACK` 以交换黑白方。
**Bug 在于这个方法被错误地触发了两次**：
当客户端获胜时，客户端会发送 `RESULT` 报文，同时也会发送 `MOVE` 报文。主机收到 `MOVE` 后在本地执行 `_apply_move`，判定游戏结束，调用了一次 `_handle_remote_game_end()`；紧接着主机处理网络队列里的 `RESULT` 报文，又调用了一次 `_handle_remote_game_end()`[cite: 1, 2]！
连续翻转两次等于没有翻转，导致第二局双方对“谁是黑方”的认知发生错乱。

### 2. 修复指令
通过引入 `session_id` 的幂等校验来防止一局内多次翻转[cite: 1, 2]。
请在 `GomokuApp.__init__` 中新增：
```python
self.role_swapped_session = -1
```

修改 `_handle_remote_game_end` 方法：

**Python**

```
def _handle_remote_game_end(self) -> None:
    if self.mode != "remote" or not self.networked:
        return
    if not self.is_host:
        return

    # 新增：防止同一局内因收到 MOVE 和 RESULT 导致多次触发翻转
    if getattr(self, 'role_swapped_session', -1) == self.session_id:
        return
    self.role_swapped_session = self.session_id

    self.remote_black_is_host = not self.remote_black_is_host
    owner = "HOST" if self.remote_black_is_host else "CLIENT"
    self._send_net(f"NEXTBLACK|{self.session_id}|{owner}")
```

---

## 二、 新增功能：战绩统计与当前身份提醒 UI

为了避免联机时的身份混淆，我们需要在右侧面板新增一个战绩显示区域。

### 1. 初始化变量

请在 `GomokuApp.__init__` 中新增统计相关的变量：

**Python**

```
self.my_wins = 0
self.peer_wins = 0
self.draws = 0
self.stats_updated_session = -1
```

### 2. 新增 UI 组件

在 `_build_ui` 方法中，在 `self.status_var` 所在的 `tk.Label` 下方，新增一个用于显示战绩的 Label：

**Python**

```
self.stats_var = tk.StringVar(value="")
tk.Label(
    side,
    textvariable=self.stats_var,
    justify=tk.LEFT,
    bg="#f5f0e6",
    fg="#1d4e89",  # 使用醒目的颜色
    font=("Microsoft YaHei", 10, "bold"),
    wraplength=200,
).pack(padx=18, pady=(0, 14), anchor="w")
```

### 3. 新增战绩更新与 UI 刷新方法

在 `GomokuApp` 类中新增以下两个方法：

**Python**

```
def _refresh_stats_ui(self) -> None:
    if self.mode != "remote" or not self.networked:
        self.stats_var.set("")
        return
  
    color_str = "黑方 (先手)" if self.my_color == Stone.BLACK else "白方 (后手)"
    stats_text = (
        f"【联机 - 第 {self.session_id + 1} 局】\n"
        f"我方执：{color_str}\n"
        f"战绩：{self.my_wins}胜 {self.peer_wins}负 {self.draws}平"
    )
    self.stats_var.set(stats_text)

def _update_stats(self, winner_color: int | None) -> None:
    if self.mode != "remote" or not self.networked:
        return
  
    # 防止一局内多次计分
    if getattr(self, 'stats_updated_session', -1) == self.session_id:
        return
    self.stats_updated_session = self.session_id

    if winner_color is None:
        self.draws += 1
    elif winner_color == self.my_color:
        self.my_wins += 1
    else:
        self.peer_wins += 1
      
    self._refresh_stats_ui()
```

### 4. 接入现有的游戏流程

请将战绩刷新逻辑嵌入到现有的状态转换中：

* **颜色分配时** ：在 `_assign_remote_colors` 方法的最后一行，调用 `self._refresh_stats_ui()` 以立即显示当前黑白方[cite: 1, 2]。
* **重新开始时** ：在 `_reset_game` 方法的末尾，调用 `self._refresh_stats_ui()` 更新局数显示[cite: 1, 2]。
* **平局时** ：在 `_on_click` 触发平局的地方 (`if all(self.board...)`)，调用 `self._update_stats(None)`[cite: 1, 2]。
* **游戏分出胜负时** ：在 `_apply_move` 方法内部：
* 当触发禁手判负时 (`if not result.legal:`)，推断出 `winner_color = Stone.WHITE if color == Stone.BLACK else Stone.BLACK`，调用 `self._update_stats(winner_color)`[cite: 1, 2]。
* 当成五获胜时 (`if result.win:`)，调用 `self._update_stats(color)`[cite: 1, 2]。

---

## 总结任务

Cline，请按照本说明书，先修复 `_handle_remote_game_end` 中的幂等 Bug（防止由于多报文到达引发的两次换边错乱），然后依次添加 `__init__`、`_build_ui` 及新的统计更新方法，并将它们挂载到生命周期函数中。完成后请简要总结你的改动。

```

***

### 沟通建议

把上面的 `Code_Review_Report_V2.md` 发给 Cline，并这样说：
> *"Cline，我测试了联机功能，第一局很好，但在第二局身份轮换的时候彻底乱套了。请读取 `Code_Review_Report_V2.md`，修复主机收到 `MOVE` 和 `RESULT` 导致的双重翻转 Bug。顺便帮我把里面提到的战绩 UI、局数统计和黑白方提示一起做进去，这样以后下棋就非常清晰了。"*
```
