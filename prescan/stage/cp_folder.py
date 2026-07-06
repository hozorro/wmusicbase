from pathlib import Path
import shutil

# ===================== 配置参数（测试时修改这里） =====================
SOURCE_MUSIC_ROOT = r"H:\musiclibcorrect"    # 真实音乐库根目录
DEST_TEST_ROOT = r"d:\tmp\music\test_music_lib"  # 存放复刻空目录结构的测试文件夹
# ======================================================================

def replicate_music_folder_structure(src_root: str | Path, dst_root: str | Path):
    src_root = Path(src_root)
    dst_root = Path(dst_root)

    if not src_root.is_dir():
        print(f"错误：源音乐库目录不存在 -> {src_root.resolve()}")
        return

    # 统计计数器
    count_area = 0
    count_char_range = 0
    count_artist = 0

    # 第一层：area 区域文件夹
    for area_src in src_root.iterdir():
        if not area_src.is_dir():
            continue
        area_dst = dst_root / area_src.name
        area_dst.mkdir(parents=True, exist_ok=True)
        count_area += 1

        # 第二层：char-range 字母分段文件夹
        for char_src in area_src.iterdir():
            if not char_src.is_dir():
                continue
            char_dst = area_dst / char_src.name
            char_dst.mkdir(parents=True, exist_ok=True)
            count_char_range += 1

            # 第三层：artist 歌手文件夹（仅创建到此层，不递归更深）
            for artist_src in char_src.iterdir():
                if not artist_src.is_dir():
                    continue
                artist_dst = char_dst / artist_src.name
                artist_dst.mkdir(parents=True, exist_ok=True)
                count_artist += 1

    print("==== 目录结构复刻完成 ====")
    print(f"目标测试目录：{dst_root.resolve()}")
    print(f"创建区域文件夹(第一层)：{count_area} 个")
    print(f"创建字母分段文件夹(第二层)：{count_char_range} 个")
    print(f"创建歌手文件夹(第三层artist)：{count_artist} 个")
    print("提示：仅复制目录骨架，无任何音乐/图片文件")

if __name__ == "__main__":
    replicate_music_folder_structure(SOURCE_MUSIC_ROOT, DEST_TEST_ROOT)
