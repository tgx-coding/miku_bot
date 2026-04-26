import requests
import os
import re


# 这里的 API 地址可以从 main.py 传进来，或者直接写死


def send_msg(msg_type, group_id, user_id, text):
    """
    发送消息到 NapCat，支持自动补全 .jpg 后缀和绝对路径
    """
    # 1. 去掉发送文本的前后空格
    text = text.strip()

    # 2. 识别并处理 [CQ:image,file=xxx]
    # 正则匹配出 file= 后面的文件名
    pattern = r'\[CQ:image,file=([^,\]]+)\]'
    matches = re.findall(pattern, text)

    for filename in matches:
        # 排除掉已经是网络链接的情况
        if not filename.startswith("http"):
            # 去掉文件名可能的空格，拼上 .jpg 后缀
            filename_clean = filename.strip()
            
            # 构造绝对路径：目录 + 文件名 + .jpg
            if not filename_clean.lower().endswith(".jpg"):
                filename_clean = f"{filename_clean}.jpg"
            
            abs_path = os.path.abspath(os.path.join(config.EMOJI_DIR, filename_clean))
            
            clean_path = abs_path.replace("\\", "/") 
            file_url = f"file:///{clean_path}"
            
            # 替换原始文本中的简易 CQ 码
            old_cq = f"[CQ:image,file={filename}]"
            new_cq = f"[CQ:image,file={file_url}]"
            text = text.replace(old_cq, new_cq)

    # 3. 根据类型选择接口和构造 payload
    if msg_type == "group":
        target_url = f"{config.NAPCAT_API}/send_group_msg"
        payload = {
            "group_id": group_id,
            "message": text
        }
    else:
        target_url = f"{config.NAPCAT_API}/send_private_msg"
        payload = {
            "user_id": user_id,
            "message": text
        }

    # 4. 执行发送
    try:
        response = requests.post(target_url, json=payload, timeout=10)
        if response.status_code == 200:
            # 这里打印处理后的 text，方便你调试路径对不对
            print(f"🚀 消息发送成功: {text}")
        else:
            print(f"⚠️ 发送失败，状态码: {response.status_code} | 响应: {response.text}")
    except Exception as e:
        print(f"❌ 网络异常: {e}")

def get_group_member_dict(group_id):
    """获取群成员名单"""
    url = f"{config.NAPCAT_API}/get_group_member_list"
    try:
        response = requests.post(url, json={"group_id": group_id}, timeout=10)
        if response.status_code == 200:
            members = response.json().get("data", [])
            return {str(m['user_id']): {
                "name": m.get("card") or m.get("nickname"),
                "role": m.get("role"),
                "level": m.get("level", "1"),
                "title": m.get("title", "")
            } for m in members}
    except Exception as e:
        print(f"❌ 获取群列表失败: {e}")
    return {}


import httpx
import config

async def approve_friend_request(flag, approve=True):
    """
    同意或拒绝好友请求
    flag: 请求事件中的 flag 字段
    approve: 是否同意
    """
    url = f"{config.API_ROOT}/set_friend_add_request" # API_ROOT 是你框架的地址，如 
    params = {
        "flag": flag,
        "approve": approve
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=params)
            if response.status_code == 200:
                print(f"✅ 已成功处理好友申请")
            else:
                print(f"❌ 处理申请失败: {response.text}")
        except Exception as e:
            print(f"❌ 调用 API 出错: {e}")


async def get_message_content(message_id):
    """根据 ID 获取消息纯文本内容"""
    url = f"{config.NAPCAT_API}/get_msg" # 或者是 /get_message
    params = {"message_id": message_id}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                # 返回原始消息字符串
                # print(f"获取消息引用: {data.get('raw_message', '')}")
                return data.get("raw_message", "")
    except Exception as e:
        print(f"⚠获取消息失败: {e}")
    return ""

async def get_forward_msg(res_id):
    """根据 res_id 获取合并转发的具体消息内容"""
    url = f"{config.NAPCAT_API}/get_forward_msg"
    params = {"message_id": res_id} # 有些框架参数名是 id 或 message_id
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                # 返回的是一个消息节点列表
                return resp.json().get("data", {}).get("messages", [])
    except Exception as e:
        print(f"❌ 获取合并转发失败: {e}")
    return []

async def send_poke(group_id, user_id):
    """
    【发送戳一戳】
    调用 NapCat API 对指定群成员执行戳一戳动作
    """
    # 优先使用配置文件的接口地址，如果没有则使用脚本内的 NAPCAT_API
    base_url = getattr(config, 'NAPCAT_API', config.NAPCAT_API)
    target_url = f"{base_url}/send_group_poke"
    
    payload = {
        "group_id": group_id,
        "user_id": user_id
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(target_url, json=payload, timeout=10)
            if response.status_code == 200:
                print(f"👉 已成功回戳用户: {user_id}")
                return True
            else:
                print(f"⚠️ 戳一戳失败，响应: {response.text}")
        except Exception as e:
            print(f"❌ 戳一戳接口异常: {e}")
    return False

