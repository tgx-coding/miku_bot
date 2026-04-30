import uvicorn
import json
import logging
import re
import asyncio
import time
import random
import os
import base64
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from datetime import datetime

# --- 导入配置 ---
import config
import Global 

# --- 子脚本导入 ---
from managers.data_manager import DM
from managers.prompt_manager import PM
from tools.ai import ask_deepseek_smart, get_balance, ask_AI, get_silicon_balance, ask_silicon_smart
from tools.network import send_msg, approve_friend_request
from tools.processor import explain_message

# --- 初始化存档 ---
DM.data_path = config.DATA_PATH
DM.load_data()
emoji_list = DM.get_emoji_list()
API_KEY = config.DEEP_SEEK_API_KEY if config.ACTIVE_MODEL == "deepseek" else config.GEMINI_API_KEY
DM.clean_old_cache(max_days=1)
ban_gp = []
LOG_THROTTLE = {}


def log_info_throttled(key, interval_sec, message):
    """Log repeating info messages at most once per interval."""
    now = time.time()
    last = LOG_THROTTLE.get(key, 0)
    if now - last >= interval_sec:
        logging.info(message)
        LOG_THROTTLE[key] = now

# ==========================================
# 后台任务与生命周期
# ==========================================

async def idle_warm_up_worker():
    """后台暖场任务"""
    logging.info("🚀 暖场守护进程已启动...")
    while True:
        now = datetime.now()
        current_hour = now.hour
        today_str = now.strftime("%Y-%m-%d")

        last_refresh = DM.data.get("last_token_refresh_date", "")
        
        if current_hour >= config.REFRESH_HOUR and last_refresh != today_str:
            logging.info(f"📅 监测到已过 {config.REFRESH_HOUR}:00，正在重置各群 Token 额度...")
            DM.data["group_token_usage"] = {}
            DM.data["last_token_refresh_date"] = today_str
            DM.save_data()

        if config.SLEEP_START <= current_hour < config.SLEEP_END:
            await asyncio.sleep(600) 
            continue

        current_time = time.time()
        for group_id, last_time in list(DM.data["last_msg_time"].items()):
            if current_time - last_time > config.IDLE_THRESHOLD:
                if random.random() < 0.3 and config.WARM_MODE: 
                    logging.info(f"检测到群 {group_id} 冷场，准备暖场...")
                    idle_prompt = config.WARM_PROMPT
                    
                    try:
                        result = await ask_deepseek_smart(messages=idle_prompt, api_key=config.DEEP_SEEK_API_KEY)
                        if isinstance(result, (list, tuple)) and len(result) >= 3:
                            reply_list, _, _ = result
                            for text in reply_list:
                                if text:
                                    send_msg("group", group_id, None, text)
                                    await asyncio.sleep(len(text) * 0.4 + 0.5)
                        DM.data["last_msg_time"][str(group_id)] = time.time()
                    except Exception as e:
                        logging.error(f"❌ 暖场调用失败: {e}")
                else:
                    DM.data["last_msg_time"][str(group_id)] = current_time - (config.IDLE_THRESHOLD - 300)
                    log_info_throttled(
                        key=f"idle_skip_{group_id}",
                        interval_sec=3600,
                        message=f"群 {group_id} 冷场中,判定未通过，跳过。",
                    )

        await asyncio.sleep(config.CHECK_INTERVAL)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("🚀 Miku 正在苏醒...")

    token_usage = DM.data.get("group_token_usage", {})
    if token_usage:
        logging.info(f"📊 已载入 {len(token_usage)} 个群聊的 Token 消耗记录")
        for gid, usage in token_usage.items():
            logging.info(f"   - 群 {gid}: 已消耗 {usage} tokens")
    else:
        logging.info("📊 当前无群聊 Token 消耗记录")

    if not hasattr(Global, 'chat_locks'): Global.chat_locks = {}
    if not hasattr(Global, 'last_handle_time'): Global.last_handle_time = {}
    bg_task = asyncio.create_task(idle_warm_up_worker())
    yield  
    logging.info("💤 Miku 准备睡觉了，正在清理任务...")
    bg_task.cancel() 
    try:
        await bg_task
    except asyncio.CancelledError:
        logging.info("✅ 后台任务已安全停止")

app = FastAPI(lifespan=lifespan)

# ==========================================
# 辅助函数模块 (解耦出的业务逻辑)
# ==========================================


def log_message(context_id, chat_contexts, sender_id, input_message):
    """
    极致压缩版：只记录最核心的对话信息，节省 Token。
    """
    # 1. 如果该上下文还没初始化，先初始化
    if context_id not in chat_contexts:
        # 这里存一个最基础的系统指令即可，详细的会在 ask_AI 前动态替换
        chat_contexts[context_id] = [{"role": "system", "content": "You are Miku cat."}]

    # 2. 构造极简的消息内容
    # 格式：用户:QQ号 说: 内容
    # 这样在 ask_AI 组装时，正则 re.search(r"用户:(\d+)") 就能生效
    clean_content = f"用户:{sender_id} 说: {input_message}"

    # 3. 存入上下文
    chat_contexts[context_id].append({
        "role": "user", 
        "content": clean_content
    })

    # 4. 保持历史长度（比如只留最近 15 条，防止内存溢出）
    if len(chat_contexts[context_id]) > 15:
        # 保留索引 0 (system) 和最后的 14 条对话
        chat_contexts[context_id] = [chat_contexts[context_id][0]] + chat_contexts[context_id][-14:]

async def handle_friend_request(data):
    """处理自动同意好友请求"""
    if data.get("request_type") == "friend":
        flag, user_id, comment = data.get("flag"), data.get("user_id"), data.get("comment")
        logging.info(f"🤝 检测到好友申请: QQ({user_id}), 验证信息: {comment}")
        await approve_friend_request(flag, True) 
        send_msg("private", None, str(user_id), "你好喵！我是猫葱，以后请多指教喵~")
        return {"status": "ok"}
    return {"status": "ignore"}

def is_admin(event: dict) -> bool:
    """
    判断发送者是否为管理层 (群主或管理员)
    """
    # 只有群消息才有权限概念
    if event.get("message_type") != "group":
        return False
    
    sender = event.get("sender", {})
    role = sender.get("role", "member")
    
    # 如果是群主或管理员，返回 True
    return role in ["owner", "admin"]

def is_owner(event: dict) -> bool:
    """
    仅判断是否为群主
    """
    return event.get("sender", {}).get("role") == "owner"

async def handle_developer_command(raw_msg, message_type, target_id, sender_id, event, group_id):
    """处理开发者及管理员特殊指令，返回 True 代表拦截，False 代表继续走 AI 对话"""
    global emoji_list
    
    # 没被提到则不走指令检查
    if f"[CQ:at,qq={config.MY_BOT_QQ}]" not in raw_msg:
        return False

    try:
        # --- 1. 开发者 (MASTER) 独占指令 ---
        if str(sender_id) == str(config.DEVELOPING_NUMBER):
            if "关闭bot" in raw_msg:
                send_msg(message_type, target_id, sender_id, "主人让我睡觉了喵，拜拜~")
                os._exit(0) 

            if "更新表情包" in raw_msg or "刷新表情包" in raw_msg:
                emoji_list = DM.get_emoji_list()
                send_msg(message_type, target_id, sender_id, "哇多了好多表情包呀，谢谢主人！")
                return True
            
            # 开发者查询 Token 消耗
            if any(k in raw_msg for k in ["token", "tk", "余额"]):
                if "qwen" in raw_msg:
                    send_msg(message_type, target_id, sender_id, "QWEN查询: https://bailian.console.aliyun.com")
                if "ds" in raw_msg or "deepseek" in raw_msg:
                    tokens = "Deepseek:" + await get_balance(config.DEEP_SEEK_API_KEY)
                    send_msg(message_type, target_id, sender_id, tokens)
                if "平均" in raw_msg:
                    d_stats = DM.data.get("decision_token_count", {"all_tokens": 0, "times": 0})
                    o_stats = DM.data.get("output_token_count", {"all_tokens": 0, "times": 0})
                    results = []
                    if d_stats["times"] > 0:
                        d_avg = d_stats["all_tokens"] / d_stats["times"]
                        results.append(f"决策层:\n  平均: {d_avg:.2f} tokens\n  总共: {d_stats['all_tokens']} tokens\n  共调用 {d_stats['times']} 次")
                    else:
                        results.append("决策层：暂无数据喵")
                    if o_stats["times"] > 0:
                        o_avg = o_stats["all_tokens"] / o_stats["times"]
                        results.append(f"输出层:\n  平均: {o_avg:.2f} tokens\n  总共: {o_stats['all_tokens']} tokens\n  共调用 {o_stats['times']} 次")
                    else:
                        results.append("输出层：暂无数据喵")
                    send_msg(message_type, target_id, sender_id, "\n".join(results))

                if "all" in raw_msg:
                    tokens = await get_silicon_balance(config.SILICONFLOW_API_KEY)
                    send_msg(message_type, target_id, sender_id, tokens)

                if any(k in raw_msg for k in ["gp", "group"]):

                    total_data = DM.data.get("total_group_usage", {})
                    daily_data = DM.data.get("group_token_usage", {})
                    
                    # 将 group_id 转为字符串，确保能匹配上字典里的 key
                    gid_str = str(group_id) 
                    
                    # 直接获取当前群的数据，如果没有则默认为 0
                    daily = daily_data.get(gid_str, 0)
                    total = total_data.get(gid_str, 0)
                    o_stats = DM.data.get("output_token_count", {"all_tokens": 0, "times": 0})
                    o_avg = o_stats["all_tokens"] / o_stats["times"]
                     
                    msg = f"当前群聊 Token 统计 ({gid_str})：\n"
                    msg += f"   今日消耗: {daily}\n"
                    msg += f"   累计消耗: {total}\n"
                    msg += f"   今日剩余token: {config.GROUP_TOKEN_LIMIT - daily}\n"
                    msg += f"   (约剩余:{(config.GROUP_TOKEN_LIMIT - daily) / o_avg:.0f} 次对话)"
                    send_msg(message_type, target_id, sender_id, msg)
                
                return True
            if any(k in raw_msg for k in ["禁言bot", "禁言BOT", "禁言Bot"]): # 管理员让 Bot 闭嘴
                if group_id not in ban_gp:
                    ban_gp.append(group_id)
                return True
            if any(k in raw_msg for k in ["解禁bot", "解禁BOT", "解禁Bot"]): 
                if group_id  in ban_gp:
                    ban_gp.remove(group_id)  
                return True  
            # if any(k in raw_msg for k in ["清空token数据", "清空token", "重制token数据","重制token"]):
                

        # --- 2. 群管理员权限指令 (非开发者也能用) ---
        if is_admin(event):
            
            if any(k in raw_msg for k in ["禁言bot", "禁言BOT", "禁言Bot"]): # 管理员让 Bot 闭嘴
                if group_id not in ban_gp:
                    ban_gp.append(group_id)
                return True
            if any(k in raw_msg for k in ["解禁bot", "解禁BOT", "解禁Bot"]): 
                if group_id  in ban_gp:
                    ban_gp.remove(group_id)   
                return True 
            if any(k in raw_msg for k in ["额度查询", "token查询", "查询token", "查询额度"]):
                total_data = DM.data.get("total_group_usage", {})
                daily_data = DM.data.get("group_token_usage", {})
                
                # 将 group_id 转为字符串，确保能匹配上字典里的 key
                gid_str = str(group_id) 
                
                # 直接获取当前群的数据，如果没有则默认为 0
                daily = daily_data.get(gid_str, 0)
                total = total_data.get(gid_str, 0)
                
                o_stats = DM.data.get("output_token_count", {"all_tokens": 0, "times": 0})
                o_avg = o_stats["all_tokens"] / o_stats["times"]
                
                msg = f"当前群聊 Token 统计 ({gid_str})：\n"
                msg += f"   今日消耗: {daily}\n"
                msg += f"   累计消耗: {total}\n"
                msg += f"   今日剩余token: {config.GROUP_TOKEN_LIMIT - daily}\n"
                msg += f"   (约剩余: {(config.GROUP_TOKEN_LIMIT - daily) / o_avg:.0f}次对话)"
                send_msg(message_type, target_id, sender_id, msg)
                
                return True


    except Exception as e:
        import traceback
        logging.error(f"❌ 开发者指令执行异常:\n{traceback.format_exc()}")
        return True 

    return False

async def process_and_send_ai_reply(reply_list, message_type, target_id, sender_id):
    """处理并拆分AI输出文本与图片，安全发送，并支持 [poke] 动作"""
    for original_text in reply_list:
        if not original_text.strip(): continue
        
        # 1. 拆分图片和文字
        parts = re.split(r'(\[CQ:image,[^\]]+\])', original_text)
        for part in parts:
            clean_part = part.strip()
            if not clean_part: continue

           # ---- 核心修改：支持 [poke] 和 [poke:123456] ----
            # 使用正则匹配这两种情况
            poke_match = re.search(r'\[poke(?::(\d+))?\]', clean_part)
            if poke_match:
                if message_type == "group":
                    from tools.network import send_poke
                    
                    # 逻辑：如果 AI 写了 QQ 号就戳那个号，没写就戳当前说话的人
                    target_user = poke_match.group(1) if poke_match.group(1) else sender_id
                    
                    await send_poke(group_id=target_id, user_id=target_user)
                
                # 清理掉所有的 poke 标记
                clean_part = re.sub(r'\[poke(?::\d+)?\]', '', clean_part).strip()
                if not clean_part:
                    continue
            # --------------------------------------------

            # 2. 处理图片 CQ 码路径
            if "[CQ:image" in clean_part:
                if "sub_type=" not in clean_part and "subType=" not in clean_part:
                    clean_part = clean_part.replace("]", ",sub_type=1]")
                clean_part = clean_part.replace("subType=1", "sub_type=1")

                match = re.search(r'file=([^,\]]+)', clean_part)
                if match:
                    file_name = match.group(1)
                    if not (file_name.startswith("http") or file_name.startswith("base64://") or ":" in file_name):
                        full_file_name = file_name if "." in file_name else f"{file_name}.jpg"
                        abs_path = os.path.join(config.EMOJI_DIR, full_file_name)
                        try:
                            with open(abs_path, "rb") as f:
                                img_data = base64.b64encode(f.read()).decode("utf-8")
                            final_file_url = f"base64://{img_data}"
                            clean_part = clean_part.replace(file_name, final_file_url)
                        except FileNotFoundError:
                            logging.error(f"❌ 找不到表情文件: {abs_path}")
                    elif file_name.startswith("file://"):
                        # 旧格式 file:// 改成 base64 重读
                        old_path = file_name.replace("file://", "")
                        if os.path.exists(old_path):
                            try:
                                with open(old_path, "rb") as f:
                                    img_data = base64.b64encode(f.read()).decode("utf-8")
                                final_file_url = f"base64://{img_data}"
                                clean_part = clean_part.replace(file_name, final_file_url)
                            except Exception:
                                pass

            # 3. 内部静默发送
            try:
                # 注意：send_msg 如果是同步的，这里直接调用；如果是异步的需要加 await
                send_msg(message_type, target_id, sender_id, clean_part)
            except Exception as e:
                logging.error(f"❌ 消息发送失败(已屏蔽外部报错): {e}")

            # 4. 模拟打字/发送延迟
            if "[CQ:image" in clean_part:
                await asyncio.sleep(1)
            else:
                delay = len(clean_part) * 0.15 
                await asyncio.sleep(min(delay, 3.0))

async def run_info_extraction(session_id, segment):
    """后台静默提取人设，兼容群聊与私聊"""
    try:
        # 1. 扫描消息里提到的所有 QQ（通常用于群聊）
        involved_info = DM.get_involved_users_info(segment)
        
        # 2. 【核心修改】如果是私聊，强制把私聊对象也塞进去
        if session_id.startswith("private_"):
            user_qq = session_id.replace("private_", "")
            # 如果档案里还没提取过这个人，或者为了更新，手动拉取一次旧档案
            if user_qq not in involved_info:
                involved_info[user_qq] = DM.data.get("user_infor", {}).get(user_qq, {})
        
        # 3. 合成 Prompt (此时 involved_info 已经包含了私聊对象)
        extract_prompt = PM.build_info_extraction_prompt(segment, involved_info)
        
        # 4. 调用 AI
        raw_res = await ask_silicon_smart(
            extract_prompt, 
            config.SILICONFLOW_API_KEY,
            model_name="deepseek-ai/DeepSeek-V2.5"
        )
        
        # 5. 解析并保存 (DM.save_extracted_info 会根据 QQ 号存入 user_infor 字典)
        if isinstance(raw_res, dict):
            content = raw_res['choices'][0]['message']['content']
            clean_json = re.sub(r"```json|```", "", content).strip()
            extracted_data = json.loads(clean_json)
            if extracted_data:
                DM.save_extracted_info(extracted_data)
                logging.info(f"🔍 [人设提取] 已更新会话 {session_id} 涉及的成员档案")
    except Exception as e:
        logging.error(f"❌ [人设提取] 失败: {e}")







# ==========================================
# 核心业务路由
# ==========================================
@app.post("/")
async def handle_event(request: Request):
    logging.debug('成功接收信息')
    data = await request.json()
    post_type = data.get("post_type")
    
    # --- 1. 变量初始化 (统一入口) ---
    raw_msg = ""
    msg_id = data.get("message_id", int(time.time()))
    group_id = data.get("group_id")
    sender_id = str(data.get("user_id", ""))
    message_type = data.get("message_type") # "group" 或 "private"
    target_id = group_id if message_type == "group" else None
    current_time = time.time()
    
    context_id = f"private_{sender_id}" if message_type == "private" else str(group_id)
    
    current_hour = datetime.now().hour
    is_sleep_time = (config.SLEEP_START <= current_hour < config.SLEEP_END)

    # 如果是消息类型，提取数据（如果是 notice 伪装过来的，这段会被跳过）
    if post_type == "message":
        raw_msg = data.get("raw_message", "").strip()
        sender_id = str(data.get("user_id", ""))
        message_type = data.get("message_type")
    # --- 2. 识别并重定向“戳一戳”事件 ---
    if post_type == "notice":
        logging.debug('检测到提示信息')
        if data.get("notice_type") == "notify" and data.get("sub_type") == "poke":
            logging.debug('检测到戳一戳')
            target_id = data.get("target_id")
            # 注意：poke 事件里的发送者键名是 sender_id，不是 user_id
            real_sender_id = str(data.get("sender_id", ""))

            # 如果被戳的是机器人自己
            if str(target_id) == str(config.MY_BOT_QQ):
                from tools.network import get_group_member_dict
                member_info = get_group_member_dict(group_id) if group_id else {}
                user_info = member_info.get(real_sender_id, {})
                sender_name = user_info.get("name", f"用户({real_sender_id})")

                logging.debug(f"👉 收到来自 {sender_name} 的戳一戳")
                
                # 【关键点】：将 notice 事件伪装成 message 变量
                # 这样下方的逻辑就会把它当成一条普通消息处理
                raw_msg = f"[系统提示：{sender_name} (QQ:{real_sender_id}) 刚才戳了戳你]"
                sender_id = real_sender_id
                message_type = "group" if group_id else "private"
                # 这里不 return，让程序继续往下走
            else:
                logging.debug('被戳的不是自己，跳过')
                return {"status": "ignore"}
        else:
            logging.debug('其他提示信息，跳过')
            return {"status": "ignore"}
        
    # 调试模式指定群聊
    if config.DEBUG_MODE:
        if group_id != config.DEBUG_GP and message_type == "group":
            logging.debug("非调试群聊，跳过")
            return {"status": "ok"}

    # 拦截黑名单的群
    if group_id in config.BLACKLIST:
        logging.debug("黑名单内群聊，跳过")
        return {"status": "ok"}
    
    # 拦截ban掉的群聊
    if group_id in ban_gp:
        logging.debug("群聊被ban，跳过")
        return {"status": "ok"}
    
    # 拦截开发者指令
    if await handle_developer_command(raw_msg, message_type, target_id, sender_id, data, group_id):
        logging.info("开发者指令，执行")
        return {"status": "ok"}


    

    # 拦截额度爆表的群聊
    if message_type == "group":
        gid_str = str(group_id)
        used_tokens = DM.data.get("group_token_usage", {}).get(gid_str, 0)
        if used_tokens >= config.GROUP_TOKEN_LIMIT and str(sender_id) != str(config.DEVELOPING_NUMBER):
            if f"[CQ:at,qq={config.MY_BOT_QQ}]" in raw_msg:
                pass
            log_info_throttled(
                key=f"token_limit_{gid_str}",
                interval_sec=1800,
                message="额度爆表群聊，跳过",
            )
                # send_msg("group", group_id, None, "呜... 猫葱好累啊，要睡觉了喵... 💤")
            return {"status": "ok"}
        
        if is_sleep_time:
            log_info_throttled(
                key=f"sleep_skip_{gid_str}",
                interval_sec=1800,
                message=f"💤 休息时间，群聊 {group_id} 仅记录不回复。",
            )
            return {"status": "ok"}


    # --- 3. 原有的消息基础拦截 ---
    # 如果既不是 notice 伪装的，也不是普通 message，就退出
    if not raw_msg and post_type != "message":
        if post_type == "request":
            return await handle_friend_request(data)
        logging.debug('非正常信息，跳过')
        return {"status": "ignore"}


    # 排除机器人自言自语
    if sender_id == str(config.MY_BOT_QQ):
        logging.debug('自己的信息，跳过')
        return {"status": "ignore"}


    if group_id:
        DM.data["last_msg_time"][str(group_id)] = current_time

    if context_id not in Global.chat_locks:
        Global.chat_locks[context_id] = asyncio.Lock()

    # ==================== 新增：记录当前会话最新收到的请求标识 ====================
    if not hasattr(Global, 'latest_req_id'):
        Global.latest_req_id = {}
    current_req_id = id(request)  # 利用请求对象的内存地址作为绝对唯一的标识
    Global.latest_req_id[context_id] = current_req_id
    # =========================================================================

    # CD 检查与时效检查
    last_time = Global.last_handle_time.get(context_id, 0) 
    if (current_time - last_time < config.REPLY_CD) or (time.time() - data.get("time", time.time()) > 30):
        if f"[CQ:at,qq={config.MY_BOT_QQ}]" not in raw_msg:
            logging.debug('冷却未完成，跳过')
            return {"status": "ignore"}

    async with Global.chat_locks[context_id]:
        try:
            # 1. 解析消息内容
            input_message = await explain_message(str(raw_msg), msg_id) 
            logging.debug("-" * 52)
            logging.debug(f"📥 收到并解析消息: {input_message}")

            # 2. 获取当前状态 
            current_feeling = DM.data.get("feeling", "无") 
            
            mood = DM.get_level_data(sender_id)
            # current_hour = datetime.now().hour
            # is_sleep_time = (config.SLEEP_START <= current_hour < config.SLEEP_END)

            # 3. 记录上下文 (仅在此处调用一次)
            log_message(
                context_id, 
                DM.data["chat_contexts"], 
                sender_id, 
                input_message
            )

            # 4. 检查是否触发人设提取 (兼容群聊与私聊)
            history = DM.data["chat_contexts"].get(context_id, [])
            
            # 初始化或递增该会话的计数 (使用 Global.session_counts 替代 Global.current_len)
            if not hasattr(Global, 'session_counts'): 
                Global.session_counts = {}
            
            # 逻辑：第一次进来按当前历史长度计，后续每条+1
            if context_id not in Global.session_counts:
                Global.session_counts[context_id] = len(history)
            else:
                Global.session_counts[context_id] += 1
            
            this_count = Global.session_counts[context_id]
            logging.debug(f"📊 会话 [{context_id}] 当前长度: {this_count} (目标触发: 每 10 条)")

            # 触发判断：每 10 条触发一次，且历史里确实有东西
            if this_count > 0 and this_count % 50 == 0:
                segment = history[-50:] if len(history) >= 50 else history
                logging.info(f"🎯 [人设提取] 命中周期，开始分析 {context_id} 的信息...")
                asyncio.create_task(run_info_extraction(context_id, segment))

            # 队列合并与跳过处理逻辑
            # 判断自己是否是等待锁的期间，最后进来的那条消息
            if Global.latest_req_id.get(context_id) != current_req_id:
                logging.debug(f"⏳ [{context_id}] 消息已被合并至上下文。检测到有更新的消息正在排队，跳过当前AI处理以加速响应。")
                return {"status": "ok"}
            

            # 4. 组装 Prompt 并询问决策层
            history_for_decision = DM.data["chat_contexts"][context_id][1:] if context_id in DM.data["chat_contexts"] else []
            chat_prompt = PM.build_decision_prompt(message_type, history_for_decision, sender_id, input_message)
            
            raw_res = await ask_silicon_smart(chat_prompt, config.SILICONFLOW_API_KEY, model_name=config.DECISION_MODEL_NAME)
            
            # 统计决策层 Token
            if isinstance(raw_res, dict):
                decision_tokens = raw_res.get('usage', {}).get('total_tokens', 0)
                if decision_tokens > 0:
                    DM.update_tokens(decision_tokens, "decision", group_id=group_id)

            if raw_res and isinstance(raw_res, dict) and 'choices' in raw_res:
                content_str = raw_res['choices'][0]['message']['content']
                reply_json = json.loads(content_str)

                if reply_json.get('should') is True:
                    logging.debug(f"[{context_id}] Miku 决定回复")
                    
                    # 1. 获取涉及到的用户 QQ (现状：recent_messages 已获取)
                    history = DM.data["chat_contexts"].get(context_id, [])
                    recent_messages = history[-10:] if len(history) > 10 else history
                    involved_qqs = {str(sender_id)}
                    for msg in recent_messages:
                        if isinstance(msg, dict):
                            content = msg.get('content', '')
                            if content:
                                match = re.search(r"用户:(\d+)", content)
                                if match:
                                    involved_qqs.add(match.group(1))
                        else:
                            # 如果发现是脏数据（元组等），打印出来方便你清理，但不让程序崩溃
                            logging.warning(f"⚠️ 跳过历史记录中的非字典消息: {msg} (类型: {type(msg)})")
                    # 2. 获取并格式化状态（交给 DM 处理，不要在 main.py 里拼字符串）
                    # 假设你在 DM 中写一个 get_compact_status 方法
                    status_table, archive_text = DM.get_compact_status_and_archive(involved_qqs)

                    # 3. 组装动态 System Prompt（完全交给 PM）
                    dynamic_system_prompt = PM.build_chat_system_prompt(
                        feeling=current_feeling, 
                        status_table=status_table, 
                        involved_users_info=archive_text,
                        emoji_list=emoji_list
                    )

                    # 4. 构造 Context：只带 1 条 System + 极简 User 历史
                    current_context = [
                        {"role": "system", "content": dynamic_system_prompt}
                    ] + history[-config.MAX_HISTORY_LIMIT:]                    
                    # logging.info("提示词：",current_context)
                    # 1. 获取 AI 回复
                    result = await ask_AI(
                        messages=current_context, 
                        api_key=config.DAW_API_KEY,
                        model_name=config.DAW_AI_MODEL_NAME
                    )

                    # 2. 解包 (确保 ask_AI 返回: 列表, 分数, 字典列表, token, 想法)
                    reply_list, score_change, reply_dic_list, usage_data, new_feeling = result

                    # 3. 更新全局状态 (统一拼写为 feeling)
                    DM.data["feeling"] = new_feeling 
                    # 如果有积分系统，在这里加分
                    # user_data["score"] += score_change 

                    # 4. 记入上下文
                    for dic in reply_dic_list:
                        DM.data["chat_contexts"][context_id].append(dic)

                    # 5. 发送 
                    await process_and_send_ai_reply(reply_list, message_type, target_id, sender_id)


                    # 统计输出层 Token 与 群计费
                    this_tokens = usage_data if isinstance(usage_data, int) else 0
                    if this_tokens > 0:
                        DM.update_tokens(this_tokens, "output", group_id=group_id)
                        if message_type == "group":
                            gid_str = str(group_id)
                            
                            # 1. 累计总额（永远不清理）
                            if "total_group_usage" not in DM.data:
                                DM.data["total_group_usage"] = {}
                            DM.data["total_group_usage"][gid_str] = DM.data["total_group_usage"].get(gid_str, 0) + this_tokens
                            
                            # 2. 当日额度（会被 worker 重置）
                            if "group_token_usage" not in DM.data:
                                DM.data["group_token_usage"] = {}
                            DM.data["group_token_usage"][gid_str] = DM.data["group_token_usage"].get(gid_str, 0) + this_tokens
                            
                            DM.save_data()
                            
                    # 结算好感度

                    new_favor = DM.add_favor(sender_id, score_change)

                    logging.info(f"💖 好感度变动: {score_change} (目标QQ: {sender_id}, 当前: {new_favor})")
                    logging.debug("-" * 52)
                else:
                    logging.debug(f"[{context_id}]  Miku 正在围观，不打算说话。")
                    logging.debug("-" * 52)

        except json.JSONDecodeError:
            logging.warning("❌ AI 决策层返回了非法的 JSON 格式，已静默拦截。")
        except Exception as e:
            # 绝对拦截，任何崩溃都不会发给QQ，只在后台打印
            logging.error(f"❌ 运行发生致命错误 (已拦截保护): {e}")
            import traceback
            logging.error("❌ 发现致命错误，正在打印堆栈追踪：")
            traceback.print_exc()
        finally:
            # 确保无论发生什么错误，CD时间都会被刷新，避免卡死或穿透漏洞
            Global.last_handle_time[context_id] = time.time()

    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8080)