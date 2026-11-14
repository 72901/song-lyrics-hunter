# API 备忘

## 网易云（主力，不需登录）

| 用途 | 接口 |
|---|---|
| 搜索 | `https://music.163.com/api/search/get?s=<urlencode>&type=1&limit=10` |
| 详情 | `https://music.163.com/api/song/detail?ids=[<ID>]` |
| 歌词 | `https://music.163.com/api/song/lyric?id=<ID>&lv=1&tv=1&kv=1` |
| 直链 | `https://music.163.com/api/song/enhance/player/url?ids=[<ID>]&br=999000` |

请求头带 `User-Agent: Mozilla/5.0` + `Cookie: appver=2.9.7` 即可，`Referer` 可选。

`fee` 字段决定能不能直链：

| fee | 含义 | 直链结果 |
|---|---|---|
| 0 | 免费 | 可拿 320k mp3 |
| 1 | VIP 专享 | `url: null`，拿不到 |
| 8 | 付费专辑 / 低音质免费 | 只给 128–320k mp3 |

**结论：除 fee:0 外，一律走 gdstudio 拿 FLAC。**

歌词返回四个字段：

- `lrc.lyric` — 主体
- `tlyric.lyric` — 中文翻译（部分曲目有，可能缺尾段）
- `klyric.lyric` — 假名注音，逐字时间轴，JSON 串，多数为空
- `transUser` — 翻译贡献者

## gdstudio 镜像（拿 FLAC 的唯一可靠途径）

```
https://music-api.gdstudio.xyz/api.php?types=url&source=netease&id=<ID>&br=999
```

```json
{"url": "https://m801.music.126.net/...flac", "br": 1030, "size": 25417626}
```

必须注意：

- **`id` 是必填**。传 `name=` 会直接报 `{"detail":"Field \`id\` is required."}`
- **必须用 curl 或带 UA 的请求**。裸 `urllib.request.urlopen` 会 403
- `br` 单位 kbps：320 = mp3；966/1030/1698/1944 = FLAC（16bit 或 24bit）
- `size` 与实际下载字节数比对，对不上说明截断
- URL 里带时间戳目录，**约 2 分钟失效**，取到就下
- 偶发限流，重试 2~3 次

也支持 `source=tencent|kugou|kuwo|migu|joox|spotify`。实测 `kuwo` 会返回
`Value of source is not supported.`；`joox` 能返回 URL 但 `size: 0` 且直链常 404，
只有 `netease` 稳定可用。

## LRCLIB（精度常更高，但 503 频繁）

| 用途 | 接口 |
|---|---|
| 精确查 | `https://lrclib.net/api/get?track_name=<..>&artist_name=<..>&duration=<秒>` |
| 模糊查 | `https://lrclib.net/api/search?q=<关键词>` |
| 按 ID | `https://lrclib.net/api/get/<id>` |

三个必须写的防御：

```python
# 1) 503 ServerOverloaded 是常态，不是错误
for _ in range(8):
    r = request(url)
    if '"syncedLyrics"' in r: break
    time.sleep(5)

# 2) 响应里可能有裸换行，strict 模式会炸
json.loads(raw, strict=False)

# 3) search 可能返回 dict（错误对象）而不是 list
d = json.loads(raw, strict=False)
if isinstance(d, dict):
    print(d.get("message")); return
```

`syncedLyrics` 带时间轴，`plainLyrics` 没有。`instrumental: true` 的别白费功夫。

**LRCLIB 不是天然更准**：同一首歌可能有 10+ 个用户上传版本，需要按
`duration` 接近音频时长来挑，再逐句实测。《渡月橋》三个候选全是 82.9%，
不如网易云的 95%。

## syncedlyrics（兜底聚合库）

```bash
sudo pip3 install --break-system-packages syncedlyrics
/usr/bin/python3.12 -c "import syncedlyrics; print(syncedlyrics.search('歌名 歌手'))"
```

- **必须用 `/usr/bin/python3.12`**，pyenv 的 3.11 里导入不到
- 聚合 LrcLib / NetEase / Musixmatch / Deezer
- Musixmatch 会刷 `Network is unreachable`，无害

## 环境相关的坑

| 症状 | 处理 |
|---|---|
| `pip` 报 `externally-managed-environment` | `sudo pip3 install --break-system-packages` |
| YouTube 全挂 `Network is unreachable` | 沙箱封锁，别试，直接网易云 |
| B 站 API 412 | 需 cookie/wbi 签名，性价比低，别耗时间 |
| 反过来 `ModuleNotFoundError: scipy` | 系统 `python3` 有 scipy/numpy，py3.12 没有 |

## 时间戳格式对照

| 写法 | 来源 | 解析方式 |
|---|---|---|
| `[00:03.17]` | 网易云 lrc | 两位 = 百分秒 → ×10 |
| `[00:03:17]` | 部分字幕站 | 第三段用冒号，同样 ×10 |
| `[00:03.170]` | 标准 LRC / LRCLIB | 三位 = 毫秒，直接用 |
| `[00:12:38]` | 《衛星》这类曲目 | 冒号分隔厘秒，**当 12.38 秒，不是 12 分 38 秒** |
| `[00:03]` | 劣化版 | 无小数，只能到秒，须换源 |

正则一把梭：`\[(\d{1,2}):(\d{2})(?:[:.](\d{1,3}))?\]`

拿到秒数后统一输出 `[{mm:02d}:{ss:02d}.{ms:03d}]`。
