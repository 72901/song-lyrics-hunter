# song-lyrics-hunter

**歌曲与时间轴歌词抓取** — 下载 FLAC 音轨 + 毫秒级时间轴歌词，并用音频人声起点做客观校验与吸附。

一条经过实战验证的流水线：

> **搜歌定版 → 下 FLAC → 取歌词 → 统一毫秒 → 人声校验 → 严格吸附 → 交付**

核心价值不在"能下到"，而在**歌词时间轴是经过客观量化校验的**，而不是抓来就交。

---

## 为什么需要它

现成的歌词源（LRC / LRCLIB / 网易云）时间轴普遍存在几十到几百毫秒的漂移。直接拿来用，卡拉OK 模式下的字幕就会明显对不上嘴型。

这个技能的做法是：**不相信歌词源，把音频本身当成标准答案**。

- FLAC 解码为 16 kHz 单声道，10 ms 一帧
- FFT 提取 300–3400 Hz 人声频段能量
- 找人声起始峰（onset），看每句歌词离最近的峰有多远
- 偏差超出容差才吸附，**吸附后复检指标**

实测《渡月橋》：原始时间轴 88% 命中 / 0.20s 平均偏差 → 吸附后 **95% 命中 / 0.03s**。

---

## 特性

| 特性 | 说明 |
|---|---|
| 版本自动定版 | 只给歌名时自动取原唱原版，不弹版本选择框 |
| 无损音轨 | FLAC 优先（24bit 优先），直链 2 分钟内失效，自动重取 |
| 毫秒时间轴 | 统一输出 `[mm:ss.mmm]`，兼容三种时间戳写法 |
| 客观校验 | 用人声峰算命中率与平均偏差，不是"看着差不多" |
| 双语对照 | 日文/中文交替两行同时间戳，支持中日双语歌词 |
| 元信息过滤 | 只在「关键词 + 冒号」时才丢制作信息，不误杀正词 |

---

## 安装

### 依赖

| 依赖 | 版本 | 用途 |
|---|---|---|
| Python | ≥ 3.9 | 脚本运行环境 |
| numpy | ≥ 1.21 | 频谱分析 |
| scipy | ≥ 1.7 | `find_peaks` 人声起点检测 |
| ffmpeg / ffprobe | 任意近期版本 | 音频解码与校验 |

```bash
pip install -r requirements.txt
# macOS
brew install ffmpeg
# Ubuntu / Debian
sudo apt install ffmpeg
# Windows
winget install Gyan.FFmpeg
```

### 放入 WorkBuddy 技能目录

```bash
git clone https://github.com/72901/song-lyrics-hunter.git
cp -r song-lyrics-hunter ~/.workbuddy/skills/
```

Windows：`%USERPROFILE%\.workbuddy\skills\`

也可以直接把整个仓库目录放进 `~/.workbuddy/skills/song-lyrics-hunter/`，`SKILL.md` 在根目录即可被识别。

---

## 使用

### 作为技能使用（推荐）

在 WorkBuddy 里直接说：

```
下载《春嵐》
```

```
帮我找《五月雨》的歌词，要时间轴的
```

技能会自己完成整条流水线并交付 FLAC + 两份 TXT。

### 作为命令行工具使用

```bash
# 1. 搜歌定版（会标注「原版候选 / 翻唱改编」）
python3 scripts/fetch_song.py search "春嵐"

# 2. 下载 FLAC（<ID> 取上一步的 ID）
python3 scripts/fetch_song.py get 1234567 --out ./音乐下载

# 3. 看网易云歌词（lrc / tlyric / klyric）
python3 scripts/fetch_song.py lyrics 1234567

# 4. 一条命令出成品（原文 TXT + 双语 TXT）
python3 scripts/build_delivery.py \
  --audio "./音乐下载/春嵐 - john feat. 初音ミク.flac" \
  --lrc lrc.lrc --tlyric tlyric.lrc \
  --title "春嵐" --artist "john feat. 初音ミク" \
  --credit "词曲：john" \
  --sections "0=【A段：虚像に塗れた私】;14=【副歌：春の嵐呼んだ】"

# 5. 复检交付结果（写入命中率与平均偏差）
python3 scripts/lyrics_sync.py "./音乐下载/春嵐 (双语歌词) - john feat. 初音ミク.txt" --json
```

`build_delivery.py` 输出 JSON，其中 `missing_rows` 必须为空 —— 非空说明网易云译文缺句，需逐句补译后重跑。

### 只做体检

```bash
python3 scripts/lyrics_sync.py <音频.flac> <歌词.txt> --report
```

输出命中率与平均偏差，不修改文件。加 `--snap --tol 0.25` 可就地吸附。

---

## 目录结构

```
song-lyrics-hunter/
├── SKILL.md                      # 技能主文档（版本规则 / 工作流 / 坑）
├── requirements.txt
├── scripts/
│   ├── fetch_song.py             # 搜歌 + 取直链 + 下载 + 完整性检查
│   ├── build_delivery.py         # 主脚本：解析+过滤+吸附+译文对齐+双份输出
│   └── lyrics_sync.py            # 人声峰校验 / 吸附 / 复检
└── references/
    ├── api-notes.md              # 网易云 / gdstudio / LRCLIB 接口备忘
    └── bilingual-format.md       # 双语歌词排版规范
```

---

## 关键指标与判定标准

| 指标 | 含义 | 阈值 |
|---|---|---|
| 命中率 | 偏差 < 0.45s 的句子占比 | < 85% 判定歌词源有问题，**换源**别硬掰 |
| 平均偏差 | 所有句子到最近人声峰的平均距离 | > 0.35s 判定歌词源有问题 |
| 吸附容差 | 一步吸附到最近人声峰的距离上限 | 默认 0.25s |

放宽到 `0.6s` 需要三条同时满足：偏差集中在 0.45–0.70s 窄带、文本与音频确认同歌、歌手唱法本身是弱起/气声/大量转音。放宽后必须复检（命中率 ≥90%、平均偏差 ≤0.1s、最大位移 ≤0.7s），任一不满足就退回 0.25。

---

## 常见坑

| 现象 | 原因 | 处理 |
|---|---|---|
| `code:-110` / `url:null` | 付费曲 | 换 gdstudio 镜像 |
| `Field id is required` | 镜像用了 `name=` 参数 | 改成 `id=<网易云ID>` |
| 下载下来只有几百字节 | 直链 token 过期 | 重新取 URL 立刻下 |
| `制作人 : john` 混进歌词 | 元信息过滤只写了裸关键词 | 改成「关键词+冒号」判定 |
| 译文整段缺失/错位 | 吸附后时间戳位移 | 按**行序窗口**对齐（±4 行，0.4s） |
| `[00:12:38]` 解析成 12 秒 | 冒号分隔的厘秒 | 宽容正则，两位 ×10 |

完整清单见 [SKILL.md](SKILL.md)。

---

## 免责声明

本项目仅供个人学习与研究使用。请遵守音乐平台的版权规定与用户协议，不要用于商业分发或批量抓取。

- 音频与歌词的著作权归原权利人所有
- 使用的镜像服务由第三方提供，其可用性不受本项目控制
- 请仅下载你有权访问的内容

## License

[MIT](LICENSE) © 72901
