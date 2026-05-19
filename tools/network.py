import requests
import os
import re
import logging
import base64
import config
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

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
        # 跳过已经是 base64 的
        if filename.startswith("base64://"):
            continue
        
        # 如果是旧格式 file://，读取后转 base64
        if filename.startswith("file://"):
            old_path = filename.replace("file://", "").lstrip("/")
            abs_path = "/" + old_path if not old_path.startswith("/") else "/" + old_path.lstrip("/")
            # 统一将后缀改为 .jpg
            if not abs_path.lower().endswith(".jpg"):
                base_name = abs_path.rsplit(".", 1)[0]
                abs_path = f"{base_name}.jpg"
            try:
                with open(abs_path, "rb") as f:
                    img_data = base64.b64encode(f.read()).decode("utf-8")
                file_url = f"base64://{img_data}"
            except FileNotFoundError:
                logging.error(f"❌ 找不到图片文件: {abs_path}")
                continue
        elif filename.startswith("http"):
            continue
        else:
            # 纯文件名：自动补全 .jpg 后缀
            filename_clean = filename.strip()
            if not filename_clean.lower().endswith(".jpg"):
                filename_clean = f"{filename_clean}.jpg"
            abs_path = os.path.abspath(os.path.join(config.EMOJI_DIR, filename_clean))
            try:
                with open(abs_path, "rb") as f:
                    img_data = base64.b64encode(f.read()).decode("utf-8")
                file_url = f"base64://{img_data}"
            except FileNotFoundError:
                logging.error(f"❌ 找不到表情文件: {abs_path}")
                continue
        
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

    # 4. 去除 URL 中可能存在的双斜杠
    target_url = re.sub(r'(?<!:)/+', '/', target_url)

    # 5. 执行发送
    try:
        response = requests.post(target_url, json=payload, timeout=10)
        # 记录日志时隐藏 base64 内容，节省空间
        log_text = re.sub(r'base64://[^,\]]+', 'base64://<图片数据已省略>', text)

        if response.status_code == 200:
            # NapCat API 即使 HTTP 200 也可能投递失败，必须检查响应体
            try:
                resp_json = response.json()
            except Exception:
                resp_json = {}

            napcat_status = resp_json.get("status", "ok")
            napcat_retcode = resp_json.get("retcode", 0)
            napcat_msg = resp_json.get("message", "")
            napcat_wording = resp_json.get("wording", "")

            if napcat_status == "failed" or napcat_retcode != 0:
                logging.warning(
                    f"⚠️ NapCat 投递失败 | HTTP 200 但业务层错误 | "
                    f"status={napcat_status}, retcode={napcat_retcode}, "
                    f"message={napcat_msg}, wording={napcat_wording} | "
                    f"发送内容: {log_text}"
                )
            else:
                logging.debug(f"🚀 消息发送成功: {log_text}")
        else:
            logging.warning(f"⚠️ 发送失败，状态码: {response.status_code} | 响应: {response.text} | 发送内容: {log_text}")
    except Exception as e:
        logging.error(f"❌ 网络异常: {e}")

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
        logging.error(f"❌ 获取群列表失败: {e}")
    return {}


import httpx

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
                logging.info(f"✅ 已成功处理好友申请")
            else:
                logging.error(f"❌ 处理申请失败: {response.text}")
        except Exception as e:
            logging.error(f"❌ 调用 API 出错: {e}")


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
                # logging.info(f"获取消息引用: {data.get('raw_message', '')}")
                return data.get("raw_message", "")
    except Exception as e:
        logging.warning(f"⚠获取消息失败: {e}")
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
        logging.error(f"❌ 获取合并转发失败: {e}")
    return []

def get_bj_time():
    return datetime.now(timezone(timedelta(hours=8)))

def send_emoji_reaction(message_id, emoji_id="124"):
    """
    在指定消息下回复系统表情
    emoji_id 示例: 124(奶茶), 66(大拇指), 128(心动)
    """
    url = f"{config.NAPCAT_API}/set_msg_emoji_like"
    payload = {
        "message_id": message_id,
        "emoji_id": str(emoji_id)
    }
    try:
        response = requests.post(url, json=payload, timeout=5)
        return response.json()
    except Exception as e:
        logging.error(f"❌ 设置表情回应失败: {e}")


def get_current_time_simple():
    """
    获取当前时间，格式为：月/日/时
    """
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    # %m: 月份, %d: 日期, %H: 小时(24小时制)
    logging.debug(now.strftime("%m-/%d /%H:/%M"))
    return now.strftime("%m-%d %H:%M")

def get_now_beijing():
    """内部逻辑判断用的 datetime 对象"""
    return datetime.now(ZoneInfo("Asia/Shanghai"))

async def get_group_member_name_dict(group_id: int) -> dict:
    """
    获取当前群聊全部成员的 {QQ号: 名字} 字典
    名字逻辑：优先使用群名片(card)，如果没有设置则使用QQ昵称(nickname)
    """
    # 根据你的 NapCat 实际端口修改（通常在一台电脑上是 3000）
    url = "http://127.0.0.1:3000/get_group_member_list"
    payload = {
        "group_id": group_id,
        "no_cache": True  # 强制刷新缓存，确保获取到最新的群名片
    }
    
    result_dict = {}

    # 1. 安全屏蔽当前请求的代理，防止本地连接抽风或引发旧版本 httpx 参数崩溃
    old_http = os.environ.get("HTTP_PROXY")
    old_https = os.environ.get("HTTPS_PROXY")
    if "HTTP_PROXY" in os.environ: del os.environ["HTTP_PROXY"]
    if "HTTPS_PROXY" in os.environ: del os.environ["HTTPS_PROXY"]

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            
            # 2. 及时恢复环境变量，不影响大模型 API 的海外代理
            if old_http: os.environ["HTTP_PROXY"] = old_http
            if old_https: os.environ["HTTPS_PROXY"] = old_https

            if resp.status_code == 200:
                res_json = resp.json()
                if res_json.get("status") == "ok":
                    member_list = res_json.get("data", [])
                    
                    for member in member_list:
                        # 转换 QQ 号为 int 类型（符合你的字典键示例）
                        qq_number = str(member["user_id"])
                        
                        # 核心命名逻辑：若群名片 card 为空或不存在，则回退使用 nickname
                        show_name = member.get("card") or member.get("nickname") or "无名群员"
                        
                        result_dict[qq_number] = show_name
                        
                    logging.info(f"📊 成功构建群 {group_id} 名册字典，共 {len(result_dict)} 个成员")
                else:
                    logging.error(f"❌ NapCat 返回状态异常: {res_json}")
            else:
                logging.error(f"❌ 获取群成员列表 HTTP 失败，状态码: {resp.status_code}")

    except Exception as e:
        # 确保发生异常时也能恢复代理环境变量
        if old_http: os.environ["HTTP_PROXY"] = old_http
        if old_https: os.environ["HTTPS_PROXY"] = old_https
        logging.error(f"❌ 构建群成员字典时遭遇严重系统异常: {repr(e)}")

    return result_dict