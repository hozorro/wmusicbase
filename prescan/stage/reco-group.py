import json
import os
import time
from pathlib import Path
import dashscope
from app.core.config import settings

# ===================== 全局配置 =====================
RAW_LIST_PATH = Path(r"d:\tmp\music\artist_list_raw.json")
FINAL_LIST_PATH = Path(r"d:\tmp\music\artist_list_with_group.json")
GROUP_CACHE = Path(r"d:\tmp\music\group_ai_cache.json")
BATCH_SIZE = 25
# Qwen 接口配置
dashscope.base_http_api_url = settings.DASHSCOPE_BASE_URL
QWEN_MODEL = settings.AI_MODEL_NAME
API_KEY = settings.AI_API_KEY
# ====================================================

ai_cache = {}

def load_cache():
    global ai_cache
    if GROUP_CACHE.exists():
        with open(GROUP_CACHE, "r", encoding="utf-8") as f:
            ai_cache = json.load(f)

def save_cache():
    with open(GROUP_CACHE, "w", encoding="utf-8") as f:
        json.dump(ai_cache, f, ensure_ascii=False, indent=2)

def chunk_list(lst, size):
    return [lst[i:i+size] for i in range(0, len(lst), size)]

def build_batch_prompt(name_batch):
    items = "\n".join([f"{i+1}. {n}" for i, n in enumerate(name_batch)])
    prompt = f"""你是音乐歌手分类专家，区分名称是【单人歌手】/【音乐组合/乐队】，严格遵守规则：
1. 单人：个人艺名、人名（周杰伦、邓紫棋、薛之谦、Taylor Swift）
2. 组合：男团、女团、乐队、双人团体（五月天、TFBOYS、凤凰传奇、S.H.E）
3. 陌生小众名称统一判定为单人

输入歌手列表：
{items}

输出要求：仅返回标准JSON数组，每个元素包含name与is_group（布尔值，组合为true，单人为false），不要任何解释、换行说明、多余文字。
输出示例：
[
    {{"name":"周杰伦","is_group":false}},
    {{"name":"五月天","is_group":true}}
]"""
    return prompt

def batch_judge(batch_names):
    current = batch_names.copy()
    while True:
        prompt_text = build_batch_prompt(current)
        messages = [
            {
                "role": "user",
                "content": [
                    {"text": prompt_text}
                ]
            }
        ]
        try:
            response = dashscope.MultiModalConversation.call(
                api_key=API_KEY,
                model=QWEN_MODEL,
                messages=messages,
                result_format="message",
                max_tokens=1024
            )
            if response.status_code != 200:
                print(f"Qwen调用失败 code:{response.code} msg:{response.message}")
                time.sleep(2)
                continue
            content = response.output.choices[0].message.content
            if isinstance(content, list):
                content = content[0]["text"].strip()
            else:
                content = content.strip()
            s_idx = content.find("[")
            e_idx = content.rfind("]") + 1
            json_str = content[s_idx:e_idx]
            res_arr = json.loads(json_str)
            if len(res_arr) != len(current):
                raise ValueError(f"输入{len(current)}个，输出{len(res_arr)}个，数量不匹配")
            map_res = {x["name"]: x["is_group"] for x in res_arr}
            return map_res
        except Exception as err:
            print(f"批次推理异常 {str(err)}，拆分减半重试")
            if len(current) == 1:
                return {current[0]: False}
            mid = len(current) // 2
            left_map = batch_judge(current[:mid])
            right_map = batch_judge(current[mid:])
            return {**left_map, **right_map}

if __name__ == "__main__":
    if not API_KEY:
        print("错误：未读取到环境变量 DASHSCOPE_API_KEY，请配置阿里云密钥")
        exit(1)
    if not RAW_LIST_PATH.exists():
        print(f"原始歌手文件不存在 {RAW_LIST_PATH}，请先运行目录提取脚本")
        exit(1)

    # 加载原始歌手列表
    with open(RAW_LIST_PATH, "r", encoding="utf-8") as f:
        artist_list = json.load(f)
    load_cache()

    # 筛选未识别歌手
    all_names = [item["name"] for item in artist_list]
    need_judge = [n for n in all_names if n not in ai_cache]
    if need_judge:
        print(f"待AI识别歌手总数：{len(need_judge)}，单批{BATCH_SIZE}个")
        batches = chunk_list(need_judge, BATCH_SIZE)
        for batch in batches:
            batch_result = batch_judge(batch)
            ai_cache.update(batch_result)
            save_cache()
            print(f"完成一批 {len(batch)} 个歌手识别，缓存已更新")

    # 拼接is_group字段输出完整json
    final_data = []
    for item in artist_list:
        item["is_group"] = ai_cache.get(item["name"], False)
        final_data.append(item)
    with open(FINAL_LIST_PATH, "w", encoding="utf-8") as f:
        json.dump(final_data, f, ensure_ascii=False, indent=2)
    print(f"分类完成，完整歌手列表输出至：{FINAL_LIST_PATH.resolve()}")
