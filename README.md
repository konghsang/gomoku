# 五子棋双人小游戏

这是一个基于 Tkinter 的双人五子棋小游戏，黑方按 Renju 风格禁手实现：三三禁手、四四禁手、长连禁手。

## 环境

已使用 conda 创建环境：

```bash
conda activate game_env
```

如果你想在别的机器上复现，也可以直接使用仓库里的 `environment.yml`：

```bash
conda env create -f environment.yml
conda activate game_env
```

## 运行

```bash
python gomoku.py
```

## 说明

黑方先手；任意一方连成 5 子即获胜。黑方如果触发禁手，会被判定为无效落子。