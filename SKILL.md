---
name: song-lyrics-hunter
display_name: 歌曲与时间轴歌词抓取
display_name_zh: 歌曲与时间轴歌词抓取
display_name_en: Song & Synced Lyrics Hunter
description: 'Download songs as FLAC plus millisecond-precision synced lyrics (LRC-style
  TXT), then validate and snap the timeline against the actual vocal onsets in the
  audio. Use whenever the user asks to download a song, 下载歌曲, 找歌词, 时间戳歌词,
  逐句歌词, 卡拉OK 歌词, or wants bilingual (Japanese/Chinese) lyric sheets.'
description_zh: 下载 FLAC 音轨 + 毫秒级时间轴歌词，并用音频人声起点做客观校验与吸附；支持中日双语对照版。默认取原唱原版。
description_en: Download FLAC audio with millisecond synced lyrics validated against vocal onsets.
category: media
version: 1.1.0
author: WorkBuddy
---

# 歌曲与时间轴歌词抓取

一条经过实战验证的流水线：**搜歌定版 → 下 FLAC → 取歌词 → 统一毫秒 → 人声校验 → 严格吸附 → 交付**。

核心价值不在"能下到"，而在**歌词时间轴是经过客观量化校验的**，而不是抓来就交。

## 版本规则（最高优先级，不要问）

> **用户只给歌名 / 歌名+歌手，没有其他要求 → 直接取「原唱原版」。**

| 情况 | 处理 |
|---|---|
| 只给歌名 | 搜到原唱原版，直接做，**不要弹版本选择** |
| 给了歌手名 | 以该歌手为原唱，取该歌手的原版录音室版 |
| 同名多曲（不同歌，时长差 >5s） | 按歌手/时长判定原唱；仍无法判定才问 |
| 用户明说「翻唱 / cover / 某个版本」 | 按用户指定 |
| 只存在翻唱、无原唱可寻 | 取最接近原曲时长的完整版，并在交付说明里点明 |

原版的判定顺序：**原唱歌手本人演唱 + 正式发行（专辑/单曲）> 时长最完整 > fee 最高（正版付费）> 播放量**。
以下一律不是原版，除非用户点名：Vocaloid 翻调、歌い手 cover、プロセカ / Vivid BAD SQUAD 等游戏内翻唱、Remix、纯伴奏、AI 翻唱、中文填词。

**版本信息必须写进交付说明**（一行即可），让用户知道拿到的是哪一版，保留反悔空间。

## 交付标准（默认，不要每次问）

| 项目 | 标准 |
|---|---|
| 音轨 | `.flac` 无损，24bit 优先 |
| 歌词 | **TXT**，`[mm:ss.mmm]` 毫秒精度，一句一行 |
| 文件名 | `<歌名> - <作者>.<ext>`，**歌名在前，作者在后** |
| 双语版 | 另存 `<歌名> (双语歌词) - <作者>.txt`，**不覆盖**纯原文版 |
| 目录 | `/workspace/音乐下载/` |

用户明确表示过：**歌词就要 TXT 原歌词**，不要默认改成 md/lrc/json。若确实需要 LRC 给播放器用，再另存一份。

## 双语歌词排版（用户点名认可的唯一格式）

日文行与中文行**交替**，两行共用同一个时间戳，段落之间插入一行小节标题：

```
《春嵐》
词曲：john
演唱：john feat. 初音ミク
时长：2:42 · 时间轴精度：毫秒（人声峰校验 吸附后命中率 100% / 平均偏差 0.03s）
==== 【A段：虚像に塗れた私】 ====
[00:14.680] 虚像に塗れた私 まるで神様みたいね
[00:14.680] 浑身布满虚像的我  简直就像神明一样呢
```

要点：
- 头部四行元信息（标题 / 词曲编 / 演唱 / 时长+精度）
- 小节标题用中文方括号【】，一行 `==== 【…】 ====`，让长歌词有呼吸感
- 译文要**意译到位**，不逐字硬译；歌词里的双关、人称、语气都要保留
- 引号台词（`「」`）在译文里保留 `「」`，明确是"别人说的话"

## 工作流

### Step 1 · 搜歌定版

```bash
curl -s "https://music.163.com/api/search/get?s=<URL编码歌名>&type=1&limit=10" \
  -H "User-Agent: Mozilla/5.0" -H "Cookie: appver=2.9.7"
```

输出 `id / name / artists / duration / fee`，按上面的**版本规则**选一条，**不要问用户**。

- **同名不同曲**很常见（VOCALOID / 翻唱 / 中文重填词）。必须核对时长，差 5s 以上基本是另一首歌。
- 用户给的歌名常有不规范写法（`森の小さいな restaurants`），先搜索再确认正确写法，别直接报错。
- 搜索结果里同一原唱常有多个 ID（不同发行商/合辑）：取 **时长最完整** 的那个。

### Step 2 · 取直链下载

网易云详情接口拿 `fee`：`fee:1` 付费曲直链必失败，`fee:8` 只能给 320k mp3。两种情况都走镜像：

```bash
curl -s "https://music-api.gdstudio.xyz/api.php?types=url&source=netease&id=<ID>&br=999"
```

- **必须带 `id`**。用 `name=` 会返回 `{"detail":"Field \`id\` is required."}`
- 用 `curl`，不要用 `urllib`（无 UA 会 403）
- 返回 `br` 是 kbps：966/1030/1698/1944 是 FLAC，320 就是 mp3
- 拿到 URL 后**立刻**下载——直链带时效 token，约 2 分钟失效

```bash
curl -sL -o "<歌名> - <作者>.flac" "<URL>"
```

下载后必查（`ffprobe` 缺失时至少验 magic）：

```bash
ffprobe -v error -show_entries format=duration,bit_rate -of default=nw=1 "<file>"
python3 -c "print(open('<file>','rb').read(4)==b'fLaC')"   # True
```

### Step 3 · 取歌词（三级降级）

1. **网易云**（最稳，含译文 `tlyric` 与假名注音 `klyric`）
   ```bash
   curl -s "https://music.163.com/api/song/lyric?id=<ID>&lv=1&tv=1&kv=1"
   ```
2. **LRCLIB**（精度常更高，但 503 频繁，必须重试循环）
   ```bash
   curl -s "https://lrclib.net/api/get?track_name=<..>&artist_name=<..>&duration=<秒>"
   ```
   - `ServerOverloaded` 就 `sleep 5` 重试，最多 6~8 次
   - JSON 里有裸换行，必须 `json.loads(raw, strict=False)`
   - `search` 可能返回 **dict 而非 list**，先判类型
3. **syncedlyrics**（兜底）
   ```bash
   /usr/bin/python3.12 -c "import syncedlyrics; print(syncedlyrics.search('歌名 歌手'))"
   ```

**换源判据**：只有当源本身命中率低（<85%）时才换源，并且要**实测对比**——LRCLIB 不是天然更好。《渡月橋》LRCLIB 三个候选都是 82.9%，反而不如网易云的 95%（放宽容差后）。

### Step 4 · 一条命令出成品

```bash
python3 scripts/build_delivery.py \
  --audio "/workspace/音乐下载/<歌名> - <作者>.flac" \
  --lrc lrcN.lrc --tlyric tlyricN.lrc \
  --title "<歌名>" --artist "<作者>" \
  --credit "词曲：X" \
  --sections "0=【A段：…】;14=【副歌：…】"
```

脚本内部：解析 → 过滤制作信息 → 日文浊点修复/NFC → 人声峰吸附（默认 0.25s）→ **译文按行序对齐** → 写两份 TXT → 打印 JSON（含 `missing_rows`）。

- 先 `--dry-run` 打印带行号清单，用行号定小节边界
- `missing_rows` 非空 → 网易云译文缺句，**逐句补译**后写进 `tlyricN.lrc` 再重跑，不许留空
- `--tol 0.6` 见 Step 6 的放宽条件
- 老脚本 `buildN.py` / `biN.py` 只作历史参考，**新歌一律用 build_delivery.py**

### Step 5 · 人声起点校验（这一步是灵魂）

不要相信歌词源。**用音频本身当标准答案**：FLAC 解成 16kHz 单声道，10ms 一帧，算 300–3400Hz 人声频段能量，找峰，看每句离最近的峰多远。

```bash
python3 scripts/lyrics_sync.py "<音频.flac>" "<歌词.txt>"
```

- **命中率**：偏差 < 0.45s 的句子占比
- **平均偏差**：所有句子到最近人声峰的平均距离

经验区间：命中率 < 85% 或平均偏差 > 0.35s → 歌词源有问题，**换源**，不要硬掰。

### Step 6 · 吸附容差策略

默认 `--tol 0.25`，一步吸附到最近人声峰。

**唯一允许放宽到 0.6 的情形**（三条同时满足）：

1. 逐句偏差集中在 **0.45–0.70s** 这一窄带，而不是散乱分布
2. 文本与音频**内容确认是同一首歌**（时长差 <2s、歌词语义对得上）
3. 歌手的唱法本身是**弱起 / 气声 / 大量转音**（倉木麻衣、手嶌葵这类）

放宽后必须复检：命中率应升到 ≥90%，平均偏差落到 ≤0.1s，且最大位移不超过 0.7s。任一不满足就退回 0.25 并如实说明。

> 实测：《渡月橋》0.25s → 88%/0.20s；0.6s → **95%/0.03s**，5 句位移全部落在字头滞后区间，判定成立。
> 反例：《たぶん》《WATER》放宽后整句被拽到错误音节，判定不成立。

### Step 7 · 交付前复检

```bash
python3 scripts/lyrics_sync.py "<音频.flac>" "<双语歌词.txt>" --json
```

双语版每句重复两行，`lines` 会是原文句数的 2 倍，属正常。命中率与平均偏差应和 Step 4 的输出一致。把命中率写进头部。

`--json` 输出里 `hit_rate` / `mean_dev` 是**当前文件**的指标，`hit_rate_before` / `mean_dev_before` 是本次处理前的原始时间轴指标。

## 常见坑（都真实踩过）

| 现象 | 原因 | 处理 |
|---|---|---|
| `code:-110` / `url:null` | 付费曲 | 换 gdstudio 镜像 |
| gdstudio 报 `Field id is required` | 用了 `name=` 参数 | 改成 `id=<网易云ID>` |
| gdstudio 403 | urllib 无 UA | 用 `curl -A "Mozilla/5.0"` |
| 下载下来只有几百字节 | 直链 token 过期 | 重新取 URL 立刻下 |
| `制作人 : john` 混进歌词 | 元信息过滤只写了「作词/作曲」 | 见下：**关键词+冒号**判定，别用裸关键词 |
| 译文整段缺失/错位 | 吸附后时间戳位移，按时间戳查表失效 | 按**行序窗口**对齐（±4 行，0.4s） |
| 译文只有前半段 | 网易云译文缺句 | 逐句补译，`missing_rows` 必须清空 |
| 文件名里带着上一首的歌名 | 复制旧脚本改参数漏改 | 用 `build_delivery.py`，别手改脚本 |
| 时间戳 `[00:12:38]` 解析成 12 秒 | 冒号分隔的厘秒 | 宽容正则 `(?:[:.](\d{1,3}))?`，两位 ×10 |
| 歌词整体偏移 0.5s+ | 源本身错 | **换源**，别改时间戳 |

**元信息过滤的正确写法**——只在「关键词 + 冒号」时才丢，否则会误杀正词（`曲がりくねった`、`movie のように`）：

```python
CREDIT_PAT = re.compile(r"^\s*(作词|作詞|作曲|编曲|編曲|制作人|製作人|producer|arranger"
                        r"|composer|lyricist|mix|mastering|illust|movie)\s*[:：]", re.I)
```

**特别注意**：觉得"官方歌词是错的"想手改时，先回头验证——《WATER》那次把正确的 `[04:49.66]` 改成错误的 `[04:53.900]`，后来靠能量值比对才发现是自己错了。**能量数据 > 直觉**。

## 收尾

- `ls -lh` 报一次三个文件大小
- `present_files` 同时给 `.flac` 与两份 `.txt`（双语版排最前）
- 交付说明里写明：**这首歌是哪个版本**、命中率/平均偏差、译文是否需要补译

## 脚本

| 脚本 | 用途 |
|---|---|
| `scripts/build_delivery.py` | **主脚本**：解析+过滤+吸附+译文对齐+双语/原文双份输出，一条命令到底 |
| `scripts/lyrics_sync.py` | 人声峰校验 / 吸附 / 复检（也可独立用于任意歌词文件） |
| `scripts/fetch_song.py` | 搜索 + 直链 + 下载 + 完整性检查一条龙 |

排版细则见 `references/bilingual-format.md`，接口备忘见 `references/api-notes.md`。
