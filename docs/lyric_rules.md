# fetch_v3 打分原则、状态判定与落盘原则

> 用于生成 `--help` 附录 / README 的权威描述。所有阈值均取自 `fetch_v3.py` 当前代码，
> 改代码时必须同步改这里（改一处、对一处，别让帮助文档撒谎）。

---

## 一、打分原则

### 0. 前置硬闸（不满足直接丢弃，连分都不打）

| 闸门 | 条件 | 说明 |
|---|---|---|
| 曲名 | `tsim < 0.82` → 丢弃 | 归一化后相似度，低于此值认为不是同一首歌 |
| 时长 | 两边都有时长且 `\|dt\| > 10s` → 丢弃 | 只卡「明显不是同一录音」，不区分版本 |
| 下架 | 候选 `status == 0` → 丢弃 | 网易云已下架 |

过了硬闸的候选都会算分，**最终取分最高的一个**，哪怕它是 `low`。
即：只要池子里有人过闸，就一定选一个出来，不存在「都不选」。

### 1. 相似度 `sim(a, b)`

先把两侧都做 `norm_key`（繁转简 → NFKC 归一 → 去括号内容 → 去空格/标点/连字符 → 小写），然后：

- 完全相同 → `1.0`
- 一方包含另一方 → `max(0.88, 短/长长度比)`（包含关系至少给 0.88）
- 其余 → `difflib.SequenceMatcher` 比率

### 2. 四个子项

| 子项 | 取值 | 说明 |
|---|---|---|
| `tsim` | 0~1 | `sim(clean_title(候选名), 本地标题)` |
| `asc` | 1.0 / 0.5 / 0.0 | 歌手精确（含官方别名 A-Lin↔黄丽玲）/ 包含（双方键长 ≥2 的子串）/ 不符；**双方任一为空、或本地是「群星/合辑/未知」→ 0.5 中性** |
| `dsc` | 1.0 / 0.6 / 0.2 / 0.5 | 时长分：\|dt\|≤2s→1.0，≤5s→0.6，≤10s→0.2；**任一侧缺时长→0.5 中性** |
| `album_sim` | 0~1 | 本地无专辑名 → 0；否则 `sim(候选专辑, 本地专辑)` |

### 3. 加权公式

```
s = 3.0 × tsim
  + 1.0 × [tsim ≥ 0.999]        # 曲名完全一致的额外奖励
  + 2.5 × asc
  + ( album_sim ≥ 0.8 ? 1.5 × album_sim : 0.6 × album_sim )
  + 3.0 × dsc
  - 扣分项
```

理论满分 **11.0**（tsim=1 + 奖励1 + asc=1 + 专辑1 + dsc=1）。实际分数保留两位小数。

**扣分项**（只在「候选有、本地没有」时扣，本地本来就是 remix/伴奏 的不会被罚）：

| 情形 | 扣分 | 触发词 |
|---|---|---|
| 垃圾版本 | **−2.5** | dj / remix / rmx / 伴奏 / 纯音乐 / 伴唱 / karaoke / instrumental / cover / 翻唱 / 原唱 / unplugged / acoustic / 重制 / remaster / radio edit / extended / 夜店 / 慢摇 |
| 版本差异 | **−1.5** | 国语版 / 粤语版 / 日语版 / 英文版 / 韩语版 / 闽南语版 / live / 现场版 / 演唱会版 / demo / 钢琴版 / 吉他版 / 纯音乐版 / 演奏版 |
| 翻唱标记 | **−2.0** | 接口返回 `originSongSimpleData`（即该条是翻唱） |

### 4. 排序与翻页

- 排序：**只按分数降序**，同分保持接口返回顺序（不额外 tiebreak）。
- 翻页：第一页 100 条（接口上限，30 会漏掉排位靠后的正版）里**最好的只有 `low`** 且还有后续页时，才翻第 2 页（`--pages` 默认 2）。绝大多数曲目一页就够。

### 5. conf 判定（严格从上往下匹配）

| conf | 条件 | 备注 |
|---|---|---|
| `high` | `tsim ≥ 0.95` **且** `asc == 1.0` **且** `dsc ≥ 1.0`（即 \|dt\|≤2s） | 必须有真实时长可比 |
| `medium`（宽松） | 仅当 `--lenient-dur N`（N>0）且 `tsim ≥ 0.95` 且 `asc == 1.0` 且 `\|dt\| ≤ N` | 记 `note=dur_lenient`，默认关闭（N=0） |
| `medium` | `tsim ≥ 0.85` 且 `asc ≥ 0.5` 且 `dsc ≥ 0.5`（即缺时长或 \|dt\|≤5s） | 兜底命中（lrcapi/lrclib 无时长）也落在这一档 |
| `low` | 其余 | 版本/歌手对不上 |

**缺时长的候选最高只能到 `medium`**，这是设计上的天花板——没有时长就没有硬证据。

### 6. conf → status（主源，完整状态机见第二节）

| conf | status | note |
|---|---|---|
| `high` / `medium` | `ok` | `dur_lenient`（若走了宽松闸），否则空 |
| `low` | `review` | `dur_diff`（`tsim≥0.95` 且 `asc==1` 且 `\|dt\|≤10`，即「歌对了只是版本时长不同」）/ 否则 `low` |

### 7. 备用源判据（比主源更严）

只有主源**明确判「没这首歌」**（`failed` 且非网络错误）才触发；备用源自己再加两道闸：

| 闸门 | 条件 |
|---|---|
| 双精确 | `tsim ≥ 0.9` **且** `asc == 1.0`（宁可漏，不可错——纯音乐的假命中全是「同名不同歌手」） |
| 时长 | 候选**自带**时长时，`\|dt\| > 3s` → 丢弃（比主源的 10s 收得更紧） |

通过后：

- `solid`（自带时长 且 `tsim≥0.95` 且 `asc==1.0`）→ `ok`
- 否则 → `review`，`note=fb_{source}_no_dur`（拿不到时长校验，只能人工看一眼）

---

## 二、状态判定原则

### 0. 五个状态

| status | 含义 | 由谁写入 | 默认重跑 | 落盘 |
|---|---|---|---|---|
| `pending` | 只有元数据，还没跑过 | `init` / `diff` 的 `DEFAULT 'pending'` | ✅ 默认就选它 | 否 |
| `ok` | 曲目对上 + 有可用歌词 + 证据足够 | 主源 `high`/`medium`、兜底 `solid`、`keep_existing`、`backfill` | ❌ | ✅ |
| `review` | 找到词但证据不足，留给人看 | 主源 `low`、兜底拿不到时长 | ❌ 需 `--status review` | 仅 `--write-low` |
| `skip` | 结论性「这首歌没有可唱的文本」 | 见 §2 的 5 个出口 | ❌ 需 `--status skip` | ❌ |
| `failed` | 没对上、或没拿到，值得再试 | 网络 / 无候选 / 全被拒 / 取词失败 / 异常 | ✅ 默认就选它 | ❌ |

- `run` 永远不会写 `pending`。
- `init` 只 upsert `path/title/artist/album/dur`，**不覆盖已有 status**（只有 `--reset` 清空整表）。
- `kept` 只是跑批时的计数器，**不是状态**；库里记的是 `ok` + `note=keep_existing`。
- 默认选行条件：`status IN ('pending','failed')`；`--status X` 覆盖它，`--force`（不带 `--status`）选全表。

### 1. 单曲判定顺序（严格自上而下，命中即停）

| 步 | 条件 | status | note |
|---|---|---|---|
| 1 | **已有文件短路**（0 请求）：未开 `--force` 且目标 lrc 存在 且开 `--keep-existing` 且文件内 `[ti:]` 与本曲标题 `sim ≥ 0.85` | `ok` | `keep_existing` |
| 2 | 推不出标题（`[ti:]` 与文件名都为空） | `skip` | `no_title` |
| 3 | 搜索请求网络出错 | `failed` | `net:<err>`（`net_error=1`） |
| 4 | 搜索无结果（带歌手查空 → 退化纯标题查空） | `failed` | `no_candidate` |
| 5 | 有结果但全被硬闸拦掉 | `failed` | `all_rejected` |
| 6 | 取歌词请求网络出错 | `failed` | `lyric_net:<err>`（`net_error=1`） |
| 7a | 歌词是占位文本（正文命中 `纯音乐/请欣赏/没有填词/暂无歌词/无歌词/not found/歌詞/歌词贡献者` 且汉字 < 30） | `skip` | `instrumental` |
| 7b | 歌词为空 / 带时间轴的有效行 < 3 | 先 `failed` → 进第 8 步 | `lyric_empty` / `lyric_too_short`（内部打 `no_lyric` 标记） |
| 8 | 兜底命中且 `solid`（自带时长 且 `tsim≥0.95` 且 `asc==1`） | `ok` | `主源<原因>`（如 `主源no_candidate`） |
| 8' | 兜底命中但非 solid（拿不到时长） | `review` | `fb_lrclib_no_dur\|主源<原因>` / `fb_lrcapi_no_dur\|主源<原因>` |
| 8'' | lrclib 返回 `instrumental` 社区标注 | `skip` | `instrumental\|主源<原因>` |
| 8''' | 兜底全无果 | 有 `no_lyric` → `skip`；否则 `failed` | `nolyric_empty` / `nolyric_too_short`；`<原因>\|兜底无果` |
| 9 | 主源拿到可用歌词 | `high`/`medium` → `ok`；`low` → `review` | `dur_lenient` / `dur_diff` / `low` |
| 10 | 任何未捕获异常 | `failed` | `exc:<类型>:<信息>`（按 `net_error` 处理，下轮重跑） |

三条硬规矩：

1. **`net_error` 永不降级成 `skip`，也永不触发兜底**。接口挂了不等于曲库没有；混在一起会把故障伪装成「全网都没有」。
2. **只有「歌找对了、但源头没有可唱文本」才记 `skip`**（第 2、7a、8''、8''' 四处）。找不到歌、全被拒、报错一律 `failed`。
3. **第 7a 的占位判定不触发兜底**。这是明确结论，再问备用源只会换来同名流行歌的假词（实测 Yanni《Secret Vows》被配过西班牙语词）。兜底里的 `placeholder` 走的是另一条路：直接当「候选被拒」，不产生 `skip`。

### 2. note 全集（status 由 note 反查）

| note | status | 触发 | 有歌词内容 |
|---|---|---|---|
| `keep_existing` | `ok` | 文件已在且标题相符 | 磁盘上的旧词 |
| `no_title` | `skip` | 标题推不出来 | 无 |
| `instrumental` | `skip` | 主源返回纯音乐占位 | 有（占位文本，不入库） |
| `instrumental\|主源no_candidate` / `instrumental\|主源all_rejected` / `instrumental\|主源lyric_empty` / `instrumental\|主源lyric_too_short` | `skip` | 主源判死 → lrclib 标注为纯音乐 | 无 |
| `nolyric_empty` | `skip` | 曲目对上但歌词空，兜底无果 | 无 |
| `nolyric_too_short` | `skip` | 同上，但有效行 < 3 | 无 |
| `dur_lenient` | `ok` | `--lenient-dur N` 收下的版本时长差 | 有 |
| `dur_diff` | `review` | 曲名歌手精确、`|dt|≤10s`，只是版本不同 | 有 |
| `low` | `review` | 其余低置信 | 有 |
| `fb_lrclib_no_dur\|主源<原因>` / `fb_lrcapi_no_dur\|主源<原因>` | `review` | 兜底命中但无时长可校验 | 有 |
| `主源<原因>` | `ok` | 兜底命中且双精确 + 有吻合时长 | 有 |
| `net:<err>` / `lyric_net:<err>` | `failed` | 接口异常（`net_error=1`） | 无 |
| `no_candidate` | `failed` | 搜索无结果 | 无 |
| `all_rejected` | `failed` | 候选全被硬闸拦掉 | 无 |
| `lyric_empty` / `lyric_too_short` | `failed` | 有词但不可用，兜底也开不了/没开 | 无 |
| `<原因>\|兜底无果` | `failed` | 主源判死且备用源无收获 | 无 |
| `exc:<类型>:<信息>` | `failed` | 未捕获异常 | 无 |
| 任意 note + `\|nofile` | 保持原 status | 有词但被策略挡下没落盘 | 有（在库里） |
| `write:<err>` | 保持原 status | 落盘 `OSError`，note 被整体替换 | 有 |

`|nofile` 是**后缀不是状态**，`stats` 的「跳过原因 / review 原因」按前缀分组，所以一条 `dur_diff|nofile` 会出现在 `dur_diff` 那一行里。

两个容易被忽略的点：

- **`skip` 行也可能带 `score/conf/source/source_id`**：第 7a 步在返回前就写好了这些字段（主源确实匹配到了、只是没有词）。所以「skip 说明匹配失败」是错的——它恰恰说明匹配成功、缺的是歌词。
- **`lyric_empty|兜底无果` 会被 `nolyric_empty` 整体替换**（`process_one` 末尾重写 note），库里的 `nolyric_*` 看不出兜底是否跑过；要判断只能看 `attempts` 和耗时。

### 3. 覆盖规则

- `run` 每次处理都会整体覆盖 `status/source/score/conf/dur_delta/cand/note`，并 `attempts+1`；`started_at` 只在第一次写入。唯一不按本次匹配结果改判的是第 1 步的短路：它不发请求、直接把 status 写成 `ok`（`note=keep_existing`），哪怕库里原来是 `skip`。
- `--dry-run` 既不落盘也不写库，状态机照跑（日志里能看到判定结果）。
- `backfill` 只碰 `status='review' AND note LIKE '%fb_%'`：命中就写盘并按 fb 结果改 status；**fb 判 `skip` 时不覆盖**（原结论有词，不能改成纯音乐）；未命中保持原样（仍带 `nofile`，可隔几天再跑）。
- `--status skip` 重跑时，`skip` 有可能变成 `ok`/`review`/`failed`——状态不是不可逆的，只有 `backfill` 对 skip 有保护。

### 4. 全库实测（最后一次 `stats`，8130 首）

| status | 数 | 占比 |
|---|---|---|
| `ok` | 6701 | 82.4% |
| `review` | 667 | 8.2% |
| `skip` | 643 | 7.9% |
| `failed` | 119 | 1.5% |
| `pending` | 0 | — |

`skip` 的构成（`stats` 只打 top6，剩下的合并显示）：`instrumental` 444、`nolyric_empty` 57、`nolyric_too_short` 56，其余约 86 是兜底判纯音乐（`instrumental|主源…`）与 `no_title`。

`review` 由两类构成：主源 `conf=low`（note 为 `dur_diff` 或 `low`，其中 `dur_diff` 是「歌对了、只是版本时长不同」）与兜底命中但拿不到时长（`conf=medium`、note 为 `fb_*_no_dur|主源…`，即「曲名歌手双精确、只缺时长证据」）。两类都值得人工扫一眼，但都不能直接当 ok 用。

**一句话**：**「对上了又有词 → ok；对上了没词 → skip；没对上或没拿到 → failed；对上但证据不足 → review。net_error 一律 failed。」**

---

## 三、落盘原则

### 1. 路径

`out = --out + (曲目相对路径去掉扩展名) + .lrc`，目录结构原样复制，写入前 `makedirs`。
例：`Chinese/A-G/周杰伦/叶惠美/03 晴天.mp3` → `<out>/Chinese/A-G/周杰伦/叶惠美/03 晴天.lrc`。

### 2. 三个写入口

| 入口 | 写什么 | 是否改 status |
|---|---|---|
| `run` | `ok` 必写；`review` 仅在 `--write-low` 时写 | 是（按本次结果覆盖） |
| `backfill` | 备用源命中即写，**包含 review** | 是（按 fb 结果），写 `\|nofile` 前的 note |
| `keep_existing` 短路 | **不写**（文件已存在且 `[ti:]` 与库内标题 `sim≥0.85`） | 记 `ok` + `note=keep_existing` |

### 3. 判定表（`run`）

| status | 有歌词 | 是否写 |
|---|---|---|
| `ok` | 有 | **写** |
| `ok` | 无歌词 | 不写（理论上不会出现） |
| `review` | 有 | 仅 `--write-low` 时写：不带参数写全部 review；`--write-low medium` 只写 `conf=medium` |
| `review` | 无歌词 | 不写 |
| `skip` / `failed` / `pending` | 任意 | **永不写** |
| `--dry-run` | 任意 | 不写、也不写库 |

`--write-low medium` 是给「兜底命中」那批用的：曲名歌手双精确，只是拿不到时长，这一档写下去是安全的；而 `low`（多半是版本/歌手没对上）写了就是错歌词。

### 4. `nofile` 标记

判定「有词但没落盘」时，库里的 note 追加 `|nofile`。它是唯一能区分
**「没有歌词」**（`nolyric_*`）和 **「有歌词但被策略挡下」**（`...|nofile`）的标记，
`backfill` 就是按 `note LIKE '%fb_%'` + `nofile` 去找待补的那批。

### 5. 写入方式与失败

- `run`：直接 `open(w)` 覆盖写，非原子（中断可能留下半截文件）。
- `backfill`：`写 .tmp` → `os.replace` 原子替换。
- 写入抛 `OSError` 时：`run` 把 note 改成 `write:<err>`，其余字段照常入库；`backfill` 计数 `n_err` 并跳过该行。

### 6. 实测分布（7055 个 lrc）

| 维度 | 分布 |
|---|---|
| 目录 | Chinese 6075 / Foreign 980 |
| 来源 | netease 6579 / lrcapi 354 / lrclib 122 |
| conf | high 5789 / medium 1266 / low **0** |

`low=0` 说明从未跑过裸 `--write-low`，低置信那批一条都没落盘——这是当前策略的直接证据。
每个文件头部都带 `[re:<source>:<id>|score=..|conf=..|dt=..|src=..]`，落盘来源可逐条追溯。

---

## 一句话记住

**打分**：「高分立即写，中分要授权，低分只入库；备用源更严，宁可漏不可错。」

**状态**：「对上了又有词 → ok；对上了没词 → skip；没对上或没拿到 → failed；对上但证据不足 → review。net_error 一律 failed。」
