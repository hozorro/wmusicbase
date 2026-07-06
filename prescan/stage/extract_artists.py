import json
from pathlib import Path

# ===================== 配置项 =====================
MUSIC_ROOT = r"d:\tmp\music\test_music_lib"       # 音乐库根目录
OUTPUT_JSON = Path(r"d:\tmp\music\artist_list_raw.json")
# ==================================================

def extract_artist_folders(root: str | Path):
    root_path = Path(root)
    if not root_path.is_dir():
        print(f"错误：音乐根目录不存在 {root_path}")
        return [], []
    
    artist_records = []
    underscore_names = set()  # 存储名称含下划线的歌手
    
    # 第一层：area 区域文件夹
    for area_dir in root_path.iterdir():
        if not area_dir.is_dir():
            continue
        # 第二层：char-range 字母分段文件夹
        for char_dir in area_dir.iterdir():
            if not char_dir.is_dir():
                continue
            # 第三层：artist 歌手文件夹（目标）
            for artist_dir in char_dir.iterdir():
                if not artist_dir.is_dir():
                    continue
                
                singer_name = artist_dir.name
                # 相对路径，统一反斜杠
                rel_path = str(artist_dir.relative_to(root_path)).replace("/", "\\")
                
                record = {
                    "name": singer_name,
                    "path": rel_path
                }
                artist_records.append(record)
                
                # 检测下划线，加入待修复清单
                if "_" in singer_name:
                    underscore_names.add(singer_name)
    
    return artist_records, sorted(list(underscore_names))

if __name__ == "__main__":
    records, bad_names = extract_artist_folders(MUSIC_ROOT)
    
    # 写入JSON文件
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    
    print(f"提取完成，共找到 {len(records)} 位歌手，文件输出：{OUTPUT_JSON.resolve()}")
    
    # 打印含下划线、需要手动还原的歌手名单
    if bad_names:
        print("\n==================== 需要手动还原下划线的歌手列表 ====================")
        for name in bad_names:
            print(f"- {name}")
        print(f"\n总计 {len(bad_names)} 个名称包含下划线，请手动修正原名后再进行AI组合识别")
    else:
        print("\n所有歌手名称不含下划线，无需手动修复")
