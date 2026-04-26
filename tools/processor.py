import re
import logging
import config
import httpx
from tools.network import get_message_content, get_forward_msg
from tools.qwen_ai import ask_vision
from managers.data_manager import DM
from managers.prompt_manager import PM
import hashlib
import time

async def get_image_hash(img_url: str) -> str:
    """
    通过下载图片并对二进制内容进行 MD5 加密，生成真正的“图片指纹”
    """
    async with httpx.AsyncClient() as client:
        try:
            # 1. 下载图片数据（设置 10 秒超时）
            resp = await client.get(img_url, timeout=10)
            if resp.status_code == 200:
                # 2. 对图片的二进制内容计算 MD5
                content_md5 = hashlib.md5(resp.content).hexdigest()
                return content_md5
        except Exception as e:
            logging.error(f"❌ 下载图片并计算 Hash 失败: {e}")
    return None

async def explain_image(img_url: str, is_emoji: bool = False):
    """
    【解释图片功能 - 增加表情包识别版】
    """
    img_key = await get_image_hash(img_url)
    if not img_key:
        return "[图片内容读取失败喵]"

    # 检查缓存 
    if "image_cache" not in DM.data:
        DM.data["image_cache"] = {}
        
    if img_key in DM.data["image_cache"]:
        cached_data = DM.data["image_cache"][img_key]
        # 兼容旧格式：如果缓存里直接是字符串，则取字符串；如果是字典，取 content
        content = cached_data["content"] if isinstance(cached_data, dict) else cached_data
        
        DM.data["image_cache"][img_key]["last_time"] = time.time()
        label = "表情包" if is_emoji else "图片"
        return f"[{label}内容: {content}]"

    # 缓存未命中
    logging.info(f"🔍 发现新{'表情包' if is_emoji else '图片'}，请求 AI 解析...")
    
    try:
        # 这里动态传递 is_emoji 参数给 Prompt 管理类
        vision_prompt = PM.get_vision_prompt(is_emoji=is_emoji) 
        ai_explanation = await ask_vision(vision_prompt, img_url, config.QWEN_API_KEY) 
        
        if ai_explanation and len(ai_explanation.strip()) > 2:
            res_text = ai_explanation.strip()
            DM.data["image_cache"][img_key] = {
                "content": res_text,
                "last_time": time.time()
            }
            DM.save_data()
            label = "表情包" if is_emoji else "图片"
            return f"[{label}内容: {res_text}]"
        else:
            return "[看不清细节喵]"
            
    except Exception as e:
        logging.error(f"❌ 识图 API 报错: {e}")
        return "[解析出错喵]"
    

async def explain_reply(reply_id: str):
    """
    【解释引用功能】
    输入参数:
        reply_id (str): 引用消息的唯一 ID。
    返回:
        str: 引用消息的实际文本内容。如果获取失败则返回空字符串。
    """
    if not reply_id:
        return ""
        
    try:
        # 从机器人框架接口获取被引用消息的原文
        referenced_text = await get_message_content(reply_id)
        if referenced_text:
            return f"(引用消息: \"{referenced_text}\")\n"
    except Exception as e:
        logging.warning(f"⚠️ 获取引用内容异常: {e}")
    return ""

async def explain_forward(forward_id: str, limit: int = 20):
    if not forward_id:
        return ""
        
    try:
        nodes = await get_forward_msg(forward_id)
        if not nodes or not isinstance(nodes, list):
            return "[无法读取转发内容]\n"

        parsed_msgs = []
        for node in nodes[:limit]:
            nickname = node.get("nickname") or node.get("name") or node.get("sender", {}).get("nickname", "未知用户")
            

            content = node.get("content") 
            if not content: # 如果 content 是空的，尝试抓取 message
                content = node.get("message", "")

            if isinstance(content, list):
                combined_text = ""
                for segment in content:
                    seg_type = segment.get("type")
                    data = segment.get("data", {})
                    
                    if seg_type == "text":
                        combined_text += data.get("text", "")
                    elif seg_type == "image":
                        img_src = data.get("url") or data.get("file") or data.get("path")
                        if img_src:
                            combined_text += f"[CQ:image,url={img_src}]"
                        else:
                            combined_text += "[图片]"
                    elif seg_type == "reply":
                        combined_text += f"[CQ:reply,id={data.get('id')}]"
                    elif seg_type == "forward":
                        combined_text += f"[CQ:forward,id={data.get('id')}]"
                    else:
                        combined_text += f"[{seg_type}]"
                content = combined_text
            elif isinstance(content, dict):

                content = str(content)



            if not str(content).strip():
                logging.info(f"\n👻 抓到空消息了！请查看这个 Node 到底长啥样:\n{node}\n")

            parsed_msgs.append(f"{nickname}: {content}")
            
        if parsed_msgs:
            header = "[这是一段转发的聊天记录预览]:\n"
            return header + "\n".join(parsed_msgs) + "\n"
            
    except Exception as e:
        logging.warning(f"⚠️ 解析合并转发异常: {e}")
    return ""


def get_explain_targets(msg: str) -> list:
    targets = []
    
    # 1. 匹配引用
    for match in re.finditer(r"\[CQ:reply,id=([^,\]]+).*?\]", msg):
        targets.append({"type": "reply", "full": match.group(0), "id": match.group(1)})
        
    # 2. 匹配合并转发
    for match in re.finditer(r"\[CQ:forward,id=([^,\]]+).*?\]", msg):
        targets.append({"type": "forward", "full": match.group(0), "id": match.group(1)})
        
    # 3. 匹配图片并区分表情包
    # 修改正则：先抓取整个 [CQ:image, ... ] 块
    for match in re.finditer(r'\[CQ:image,([^\]]+)\]', msg):
        full_cq = match.group(0)
        content = match.group(1)
        # logging.info(f"DEBUG: 收到图片/表情包 CQ 码 -> {full_cq}") # 看看有没有 subType=1
        # 提取 URL (从 content 中找 url=xxx)
        url_match = re.search(r'url=([^,\]]+)', content)
        if url_match:
            img_url = url_match.group(1).replace("&amp;", "&")
            
            # 关键判断：是否存在 subType=1
            is_emoji = "sub_type=1" in content
            
            targets.append({
                "type": "image", 
                "full": full_cq, 
                "url": img_url,
                "is_emoji": is_emoji  # 新增标志位
            })
        
    return targets

async def explain_message(raw_msg: str, msg_id, max_depth: int = 5) -> str:
    """
    【总解析函数】
    输入一个 message，循环遍历和解释里面的图片、引用、转发。
    自动处理多重嵌套，直到不再包含任何 CQ 码。
    """
    current_msg = raw_msg
    depth = 0
    # 在 main.py 解析消息的地方
    

    # 1. 获取第一批要解释的信息列表
    targets = get_explain_targets(current_msg)
    
    # 2. 只要列表里有东西，并且没超过最大套娃层数，就继续循环
    while len(targets) > 0 and depth < max_depth:
        
        for target in targets:
            # 防御机制：如果这个 CQ 码已经被替换掉了，跳过
            if target["full"] not in current_msg:
                continue
                
            if target["type"] == "reply":
                explanation = await explain_reply(target["id"])
                if not explanation: explanation = "[引用内容获取失败]\n"
                current_msg = current_msg.replace(target["full"], explanation)
                
            elif target["type"] == "forward":
                # 这里调用的是你写的那个带防御逻辑的 explain_forward
                explanation = await explain_forward(target["id"])
                if not explanation: explanation = "[转发内容获取失败]\n"
                current_msg = current_msg.replace(target["full"], explanation)
                
            elif target["type"] == "image":
                explanation = await explain_image(target["url"], is_emoji=target.get("is_emoji", False))
                if not explanation: explanation = "[图片内容读取失败]\n"
                current_msg = current_msg.replace(target["full"], explanation)
        
        # 3. 每一轮结束后，重新扫描看有没有新出现的“套娃”内容
        targets = get_explain_targets(current_msg)
        depth += 1
        
    if depth >= max_depth:
        logging.warning(f"⚠️ 达到最大嵌套解析深度({max_depth}层)")

    return f"消息ID:{msg_id} 消息内容: {current_msg}".strip()

def build_info_extraction_prompt(segment, existing_info):
    history_text = "\n".join([f"{m['role']}: {m['content']}" for m in segment])
    info_ref = "\n".join([f"QQ:{u} 已有设定:{i}" for u, i in existing_info.items()])
    
    return (
        f"你是档案管理员。请分析最近10条对话，提取成员的新设定（名字、爱好、习惯等）。\n"
        f"【已知参考】\n{info_ref}\n"
        f"【对话记录】\n{history_text}\n"
        f"请输出JSON格式: {{\"QQ号\": \"提取的一句话新设定\"}}。若无新发现，只输出 {{}}。"
    )