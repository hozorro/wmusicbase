# fetch_v3 — 歌词抓取 v3

面向「远程音乐库元数据 + 低频网易云接口」的歌词抓取。

| 项目 | 说明 |
|---|---|
| 曲目信息来源 |  服务器导出的 json，不碰音频 |
| 依赖 | Python 标准库 + **opencc（繁简折叠，建议装）** |
| 内嵌歌词 | 忽略 |
| 备用源 | 只做主源失败后的串联补偿（默认 lrclib → lrcapi，可 `--fallback off`） |
| 并发 | 单线程，全局串行 |
| 请求间隔 | 默认 31s / 请求（备用源不占用） |
| 断点 | 每首 commit |
| 通知 | 飞书（启动/进度/熔断/退出） |

> **opencc 不是可选项**：接口返回繁体艺人名（岚 → 嵐、將心打開 等）时，靠 `opencc` 的 t2s
> 把两边折成同一形态才能匹配。缺它时脚本不会报错，只会静默降级——歌手分判 0，
> 这一批歌全部沉到 `review`（实测 `岚/Lucky Man`：`asc 0→1` 后 8.5/low 变 11.0/high）。
> 装法：`pip3 install opencc-python-reimplemented`（纯 Python，无需编译）。装不上会退回
> `zhconv`，两者都没有时启动日志会打红字告警。
> 注意 Windows 上 `pip install opencc` 装的是同名不同包，用 `opencc-python-reimplemented` 更稳。


打分、曲名清洗、歌词校验、LRC 头格式与 v2 **完全一致**，两版可以混用同一批输出。

唯一的口径变化：已经没有歌可唱的曲目不再记 `failed`，改为 `skip`——纯音乐记 `instrumental`，匹配对了但源头查无歌词记 `nolyric_*`。这样失败统计里剩下的才是真正需要补的曲目，重跑也不会为它们反复白花请求。

## 部署（Ubuntu）

```bash
# 0. 繁简折叠要用（否则繁体艺人名整批判 review）
pip3 install opencc-python-reimplemented

# 1. 只拷两个文件，不需要 pip install
scp _work/fetch_v3.py  music@host:/opt/lrc/
scp -r _work/deploy    music@host:/opt/lrc/

# 2. 导入元数据（可反复执行，增量更新）
cd /opt/lrc
python3 fetch_v3.py init --meta tracks.json

# 3. 看规模与预估
python3 fetch_v3.py stats

# 4. 先抽样 3 首，确认匹配质量
python3 fetch_v3.py run --limit 3 --dry-run

# 5. 正式开跑
python3 fetch_v3.py run --out /opt/lrc/lrc
```

systemd 常驻：

```bash
sudo cp /opt/lrc/deploy/fetch_v3.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now fetch-v3
journalctl -u fetch-v3 -f          # 看实时日志
sudo systemctl stop fetch-v3       # 优雅停止，进度已落库
```

## 输入 json

期望形如：

```json
[{"path":"Chinese/A-G/Beyond/乐与怒/01 我是愤怒.mp3",
  "title":"我是愤怒","artists":["Beyond"],"album":"乐与怒","duration":252.16}]
```

字段名做了宽容探测，下面这些都能认：

| 字段 | 可接受的键名 |
|---|---|
| 路径（必需） | `path` `rel_path` `relpath` `relative_path` `file` `filename` |
| 标题（必需） | `title` `name` `song` `song_title` `track_title` |
| 歌手 | `artists` `artist` `singer` `performer`（数组或 `"A/B"` 字符串） |
| 专辑 | `album` `album_name` `album_title` |
| 时长 | `duration` `dur` `length` `time`（秒 / 毫秒 / `"4:12"` 都行） |

包装形式也认：裸数组、`{"tracks":[...]}`、JSON Lines。`init` 会打印它识别到的字段映射和缺失统计，第一行就对不上会直接报错，不会静默跑歪。

`duration` 缺失也能跑，但**时长是权重最大的匹配信号**（3 分），缺了之后置信度整体下移，建议尽量带上。

## 请求频率与候选池

`--gap` 默认 31s，`--gap-mode request`（默认）表示**每一个 HTTP 请求**都间隔 31s：

```
第 N 首：search(31s) → lyric(31s) → 第 N+1 首
```

每首约 62s，7700 首 ≈ 132 小时（5.5 天）。启动时会把预估打进日志和飞书。若个别曲目需要翻页（见下），会再多一次请求，实际总时长略高。

`--gap-mode song` 则是**每首只等一次**：本首开始前等满 31s，随后这首内部的 2~3 个请求（搜索、翻页、取歌词、网络重试）连续发出：

```
第 N 首：wait(31s) → search → lyric → 第 N+1 首：wait(31s) → ...
```

每首约 31s，总时长减半（约 2.7 天），但**实际请求频率是 request 模式的 2~3 倍**，触发 `code=405` 的概率更高。启动日志会打红字提醒，跑起来后看 `stats`/飞书里的"限流冷却次数"：明显上升就把 `--gap` 调大（比如 45）或切回 `--gap-mode request`。**新接口/新主机先用默认模式跑一段**——31s 的成本远低于被限流后成批失败重来。

> 早期版本的 `--gap-mode` 只改了 ETA 估算、实际仍按每请求等待，等于开关无效；现已修正，两种模式的行为与日志里的预估一致。

### 候选池必须 100，这是 v1 错配的根因

实测这个第三方接口的搜索排序极差：`晴天 周杰伦` 的前 93 条全是翻唱，正版《晴天》(id 186016) 排在第 **94** 位。`limit=30` 时整个结果集里根本没有正版——v1 拿 `limit=1` 直接取第一条，等于专挑翻唱。

所以 v3 默认 `--cand 100`（接口上限，超过返回空）。100 条 ≈ 150KB，局域网内无压力。

第一页仍然找不到 `medium` 以上结果时，才继续翻到第二页（`--pages 2`）。绝大多数曲目一页搞定，只有被翻唱淹没的才多花一次请求。

搜索词固定为 `标题 歌手`（歌手是"群星/合辑"之类时只用标题），带歌手查不到才退化为纯标题。

### 歌手别名：只用字符串比对会废掉一整批歌

本地标签常写艺名，网易云却把曲目挂在**本名**下：

```
本地     有一种悲伤 / A-Lin   / A-Lin 原声带 / 237.4s
接口返回  有一种悲伤 / 黄丽玲 / A-Lin原声带 / 237.1s
```

歌名完全一致、专辑一致、时长差 0.3 秒，唯一对不上的是歌手名。而 `artists_score` 一旦返回 0，`conf` 就掉到 `low` → `review` → 不落盘。实测 A-Lin 整张碟 3 首全中这个坑，score 卡在 8.5 上不去。

好在 `cloudsearch` 的 `ar[].alias` 里有官方别名（`{"name":"黄丽玲","alias":["A-Lin"]}`），直接拿它做匹配即可，不需要维护别名表。命中时 `detail.alias=1`，日志里能看出是靠别名对上的。

同一逻辑覆盖 G.E.M. ↔ 邓紫棋、S.H.E ↔ 任家萱等所有"艺名/本名"分离的歌手。**这条不是可选项**——少了它，库里所有以艺名标注的歌手都会被判 `review` 而不落盘。

### 被限流（code=405）会自动冷却

接口限频时**不报 HTTP 错误**，而是返回 `HTTP 200` + body `{"code":405}`。这个坑必须在解析前拦住：否则会被当成"查到了但没这首歌"，直接把这歌记成 `failed`，白白烧掉一首。

处理方式：

```
收到 code=405
  → 全流程暂停 20 分钟（官方口径 15 分钟可恢复，这里保守加 5 分钟）
  → 推送飞书提醒（含预计恢复时刻）
  → 冷却结束重试同一个请求，对上层完全无感，成功的歌不会记失败
```

- 冷却期间**不发任何请求**。继续探只会延长限频窗口，31s 一次地试探是最坏的做法。
- 冷却**不消耗普通重试次数**，也不是 `net_error`，不会触发备用源（备用源不能顶替"接口挂了"）。
- 冷却等待可被 `systemctl stop` 秒级打断，进度不丢。
- 同一首歌最多冷却 3 次（默认 60 分钟）后放弃，记 `failed/net:code405`。
- **连续 2 首**都在冷却后仍 405，判定限流未解除，直接熔断停止并发飞书告警。否则每首都空等一小时，7500 首能拖成几个月。

可调（一般不用动）：

```bash
COOLDOWN_405=1200        # 冷却秒数，默认 20 分钟
COOLDOWN_405_MAX=3       # 单曲最多冷却几次
```

`stats` 与每次退出的飞书消息都会带上本轮累计冷却次数和总时长，据此判断是否需要把 `--gap` 调大。

## 状态机

```
pending ──> ok       高/中置信，已写 lrc
        ├─> review   低置信，默认不写文件，候选留在库里（--write-low 可写）
        ├─> failed   主源与备用源都拿不到合格歌词 / 网络错误
        └─> skip     没有标题 / 判定为纯音乐 / 源头查无可用歌词
```

`skip` 的三种 `note`：

| note | 含义 |
|---|---|
| `instrumental` | 纯音乐（网易云占位「纯音乐，请欣赏」或 LRCLIB 标注 `instrumental`） |
| `nolyric_empty` | 曲目已匹配对，但源头这条歌词是空的，兜底也没捞到 |
| `nolyric_too_short` | 同上，歌词只有零星一两行 |

`nolyric_*` 曾经记 `failed`，结果每一轮重跑都要为它白花两个请求换回同样的空结果，所以改成终态 `skip`。判定顺序是**先让兜底源试一次**（lrclib 有正经歌词的情况不少），兜底也无果才落 `skip`。

`review` 里混着两类完全不同的东西，`--write-low` 可以按置信度区分：

| 来源 | conf | 含义 | 建议 |
|---|---|---|---|
| 网易云 low | `low` | 多半是版本/歌手没对上，写了就是错歌词 | 人工过一遍 |
| lrcapi/lrclib 兜底 | `medium` | 曲名歌手双精确，只是拿不到时长校验 | 可批量收下 |

```bash
python3 fetch_v3.py run --status review --write-low medium   # 只收兜底命中
python3 fetch_v3.py run --status review --write-low          # 全收（含网易云 low，谨慎）
```

- 每首完成立刻 `commit`，进程被杀只丢当前这一首。收到 SIGTERM/Ctrl+C 时最多 1 秒内退出并收尾。
- 目标 `.lrc` 已存在且头部 `[ti:]` 与本地曲名相似（≥0.85）时自动跳过并标 `ok`，不会覆盖已有好文件。
- 重跑失败项：`run --status failed`
- 全部重做：`run --force`

**注意**：`[ti:]` 写的是本地曲名，所以 v1 留下的旧文件也会被判为"已有且正确"而跳过。要覆盖工作区里已有的 lrc，必须两个开关一起给：

```bash
python3 fetch_v3.py run --force --no-keep-existing
```

`review` 状态下 `note` 有两种：

- `dur_diff` —— 曲名歌手都精确命中，只是现场版/精选版与录音室版时长差 5~10s。大概率歌词是对的，人工一眼可判。
- `low` —— 其它低置信情况。

抽样确认 `dur_diff` 的内容确实都对后，用 `--lenient-dur 10` 把这类放宽到 `medium`（status=`ok`，note 标 `dur_lenient` 便于事后抽查）。注意它只放宽「曲名 `tsim≥0.95` + 歌手 `asc==1.0` + 时长差 ≤N 秒」这一种情形，其余判级不变：

```bash
# 只回头收 dur_diff 这一批（review 默认不会被重跑，必须显式指定）
python3 fetch_v3.py run --status review --note dur_diff --lenient-dur 10 --out /data/lyrics
```

想让它成为长期口径，再加到 systemd 的 `ExecStart` 里即可。

按 `note` 过滤是通用能力，排查各类残留很方便：

```bash
python3 fetch_v3.py run --status review --note fb_lrcapi_no_dur   # 只重跑 lrcapi 无时长命中
python3 fetch_v3.py run --status failed  --note all_rejected      # 只重跑候选全否决
```

## 备用源（主源失败后）

网易云没有的曲子不能就这么扔了。主源明确判定「搜不到 / 候选全被否决 / 歌词不合格」时，按 `--fallback` 顺序补一次：

| 源 | 召回 | 精确度 | 特点 |
|---|---|---|---|
| `lrclib`（默认首位） | 低（实测 26%，中文 38%） | **命中即对（抽样 16/16 全对）** | `/get` 是纯曲目+歌手+专辑+时长四元组精确查询，404 就是真没有。有社区标注的 `instrumental` 标记。不占网易云的 31s 配额 |
| `lrcapi`（默认次位） | 高（实测 87%） | 需严判 | 聚合酷狗/QQ，中文强。但会给不相干的歌——同名不同歌手、纯音乐配流行歌词。LRC 里 `[total:]` 恒为 0，**无法校验时长** |

不是「并联投票」，是「串联补偿」：主源拿到 medium 以上就直接用，备用源一次都不会被调用。

三条闸门（比主源更严）：

1. 曲名与歌手必须**双精确**（`tsim≥0.9`、`asc==1.0`）。纯音乐的假命中全是「同名不同歌手」——Bandari《New Morning》→ Bob Dylan、《Frozen in Time》→ Adam Green——靠这条整批挡下。
2. 能拿到精确时长时，偏差收紧到 3s（主源允许 10s）。
3. 拿不到时长（lrcapi）的命中**一律 `review`**，`note` 标 `fb_lrcapi_no_dur`，方便复核时优先看。

置信度封顶：

- `lrclib` 有精确时长且吻合 → 与主源 `high` 同质，可落 `ok`
- `lrcapi` 无时长可校验 → 最高 `review`

**纯音乐短路**：`lrclib` 返回 `instrumental` 时直接记 `skip/instrumental`，不再问 `lrcapi`。这一步很关键——实测 Yanni《Secret Vows》在 `lrclib` 被标为纯音乐，而 `lrcapi` 会给它配上一段西班牙语歌词。网易云自己返回「纯音乐，请欣赏」占位时同样直接 `skip`，不算失败。

62 首刻意挑「网易云最容易缺」的样本（法/英外文、纯音乐、冷门碟）实测：

```
救回 40/62 (65%)   判定纯音乐 8   未中 14
来源 lrclib=20（全 ok）  lrcapi=20（全 review）
均 3.2s/首
```

成本核算：备用源只在失败时触发，不占 31s 配额。即使全库 15% 失败（约 1150 首），也只多花 1 小时左右，相对 132 小时可以忽略。

配置：

```bash
export LRCLIB_API=https://lrclib.net/api     # 默认值
export LRCAPI=http://127.0.0.1:28883         # 默认值；起不来会自动跳过
python3 fetch_v3.py run --fallback lrclib,lrcapi   # 默认
python3 fetch_v3.py run --fallback lrclib          # 只用 LRCLIB，最保守
python3 fetch_v3.py run --fallback off             # 关掉，失败即 failed
```

> `lrcapi` 在 Ubuntu 上需要单独跑（`docker run -p 28883:28883 hisune/lrcapi`）。启动时会探测端口，连不通就跳过该源并写日志，不会每首都白等超时。

`stats` 会分开统计来源，兜底占比一目了然：

```
来源分布：netease=6812  lrclib=138(兜底)  lrcapi=96(兜底)
跳过原因：instrumental=203  no_title=2
```

## 补写已命中的 review（backfill）

`review` 默认不落盘，所以 lrcapi 命中那批（note 形如 `fb_lrcapi_no_dur|nofile`）需要单独补写：

```bash
# 先数一数（review 里混着网易云 low 和兜底命中，别一个字都写）
sqlite3 v3.sqlite "SELECT COUNT(*) FROM tracks WHERE status='review' AND note LIKE 'fb_lrcapi_no_dur%'"

# 只跑 lrcapi（这批本来就是 lrcapi 命中的），1 个请求/首
python3 fetch_v3.py backfill --note fb_lrcapi_no_dur --fallback lrcapi --fb-gap 1 --out /data/lyrics

# 复核：不应再有带 nofile 的行
sqlite3 v3.sqlite "SELECT COUNT(*) FROM tracks WHERE note LIKE '%nofile%'"
```

三个要点：

- **不走主源。** 用 `run --status review` 补写会重打网易云（62s/首，355 首 ≈ 6 小时），还可能把原本 medium 的判级改成 low；backfill 直接调备用源，lrcapi 是本地的，不占 31s 配额。
- **写完状态仍是 `review`**，只是 note 去掉尾部 `|nofile`。review 的意思是「没通过时长校验」，写没写文件是另一维，不要混。lrcapi 的 `[total:]` 恒为 0，这批文件天生没有时长校验。
- **幂等**：文件已存在且 `[ti:]` 与曲名相符 → 不发请求，只清 `nofile`；没命中的行保持原状（note 不变），过几天再跑一遍往往就有（LRCLIB 收录会变）。

## 输出

`<out>/<相对路径>.lrc`，保留原文件名与目录结构。

```
[ti:我是愤怒]
[ar:Beyond]
[al:乐与怒]
[length:04:12]
[re:netease:347344|score=11.0|conf=high|dt=+0.0|src=我是愤怒 / Beyond / 乐与怒]
[00:00.000] 作词 : 黄贯中
...
```

`[re:]` 是可以完整回溯的指纹：来源、歌曲 id、得分、时长偏差、以及匹配到的**原始** 曲名/歌手/专辑。播放器会忽略这一行，但排查错配时它是唯一的线索。

网易云歌词自带 `作词/作曲/编曲/制作人` 等 credit 行，v3 **原样保留**——后续 `strip_lrc.py` 才是清洗环节，抓取阶段不做有损处理。

## 飞书

内置了自定义机器人实现，只要设 `FEISHU_WEBHOOK`（开了签名就再设 `FEISHU_SECRET`）即可。

你已有的脚本可以直接复用：确保里面有 `send_feishu_msg(message)`，然后

```bash
export FEISHU_PY=/opt/lrc/你的脚本.py
```

放在脚本同目录并命名 `notify.py` 也会被自动加载。推送失败只写日志，不影响抓取。

推送节点：启动、每 50 首或每 30 分钟（取先到者）、连续 20 首网络失败熔断、正常完成、收到信号中断。

## 分机合并（A 跑 Chinese、B 跑 Foreign）

两台机器各自写自己的 `v3.sqlite`，用 `merge_v3.py` 把 B 的结果并进 A。

```bash
# 1. B 上导出（服务不用停，脚本会连 -wal 一起搬）
ssh b-host 'sqlite3 /home/abc/scripts/fetch_lyric/v3.sqlite ".backup /tmp/b.sqlite"'
scp b-host:/tmp/b.sqlite /home/abc/scripts/fetch_lyric/

# 2. A 上合并（先停服，避免抢写锁）
sudo systemctl stop fetch-v3
cd /home/abc/scripts/fetch_lyric
python3 merge_v3.py --src b.sqlite --prefix Foreign/ --dry-run   # 先看会改什么
python3 merge_v3.py --src b.sqlite --prefix Foreign/ --verify-out /data/lyrics
python3 fetch_v3.py stats
sudo systemctl start fetch-v3

# 3. 歌词文件另搬（库只是元数据）
rsync -av --ignore-existing b-host:/data/lyrics/Foreign/ /data/lyrics/Foreign/
```

合并规则（`path` 主键）：`ok(4) > review(3) > skip(2) > failed(1) > pending(0)`，
**源库状态严格更高才覆盖**；目标库已是 `ok` 的一律保留（文件在 A 上），要无条件覆盖加 `--force`。
默认不搬 `pending`（那是「还没跑」，搬过来只会让 A 以为要重跑）；`--include-pending` 才带上。
`attempts` 累加，`started_at` 保留 A 的。目标库自动备份成 `v3.sqlite.bak-YYYYmmdd-HHMMSS`，
源库只读（复制到临时目录再读，连 `-wal` 一起），写库在一个事务里，失败回滚。

`--verify-out` 会核对库里 `ok` 的行在 `/data/lyrics` 下是否真有 `.lrc`，用来确认 rsync 是否到位。

## 排查

```bash
python3 fetch_v3.py stats                 # 各状态计数 + 剩余预估
python3 fetch_v3.py export --out r.csv    # 导出全部结果
python3 fetch_v3.py export --out r.csv --status review   # 只看低置信
```

日志在 `logs/fetch_v3_YYYYMMDD.log`，跨天自动切文件。

### 日志怎么读

每首都会打一行结果（`ok`/`review` 带歌词，`skip`/`failed` 只带 note）：

```
[2/154] ok/high Foreign/O-T/Olly Murs/24 Hrs/13 That Girl.mp3  dt=0.0
[7/154] skip    Foreign/O-T/.../xx.mp3  <- instrumental        # 纯音乐，不写文件
[8/154] failed  Foreign/O-T/.../yy.mp3  <- no_candidate|兜底无果
```

等待行看前缀区分层次：

- `… 每首间隔 29.9s` —— song 模式下每首开头的一次等待（主源 31s 配额；本首内不再等）
- `… 限速等待 X` —— 其它等待：request 模式下主源的每个请求（X≈31s），或备用源（X ≤ 备用源间隔，默认 11s）

`请求失败(http503｜lrclib)，3s 后重试` 带源标签（netease / lrclib / lrcapi）。判断是哪一层：
两条重试之间夹着 `限速等待` 且数值明显小于 31s → 备用源；song 模式下主源失败时两条重试之间**什么都不打**（本首内不等待）。

`review` / `failed` 行的 `cand` 字段存了前三个候选（`曲名·歌手·时长#id`），人工判断很快——多数情况一眼就能看出是"翻唱版抢了第一"还是"根本没这首歌"。`pages` 字段记录这次翻了几页，可用来评估候选池够不够。
