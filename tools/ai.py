import httpx
import json
import logging
import config
import Global
import re
from managers.data_manager import DM


async def get_balance(api_key):
    """查询余额"""
    headers = {"Authorization": f"Bearer {api_key}"}
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{config.DEEP_SEEK_BASE_URL}/user/balance", headers=headers)
            data = response.json()
            if data.get("is_available"):
                info = data["balance_infos"][0]
                return f"当前余额：{info['total_balance']} {info['currency']}"
            return "无法获取余额信息"
        except Exception as e:
            return f"查询失败: {e}"

    
async def ask_deepseek_smart(messages, api_key):
    global chat_contexts

    
    # logging.info(
    #     "输入提示词：",
    #     messages,"/n",
    # )
    try:
        async with httpx.AsyncClient() as client:
            # 在这里我们不改变其他逻辑，但可以给 AI 一个提示，让它重点关注 reply
            response = await client.post(
                f"{config.DEEP_SEEK_BASE_URL}/chat/completions",
                json={
                    "model": "deepseek-chat", 
                    "messages": messages,
                    "response_format": {"type": "json_object"},
                    "max_tokens": 512, # 聊天不需要 1024 那么长，缩短点更快
                    "temperature": 0.7 # 增加一点随机性，防止复读
                },
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=60.0
            )
            
            res_data = response.json()
            if "choices" not in res_data:
                return "Miku 走神了喵...", 0

            raw_content = res_data['choices'][0]['message']['content']
            
            try:
                res_json = json.loads(raw_content)
                reply_text = res_json.get("reply", "喵？").strip()
                score_change = res_json.get("score", 0)
            except:
                reply_text = raw_content.strip()
                score_change = 0

            # 存储助手回复时，也只存纯文本，不存 JSON，节省 Token
            #chat_contexts[gid].append({"role": "assistant", "content": reply_text})

            reply_text_list  = reply_text.split(config.SEPARATOR)
            reply_dic_list = []
            for text in reply_text_list:
                reply_dic_list.append({"role": "assistant", "content": text})

            return reply_text_list, score_change, reply_dic_list

    except Exception as e:
        logging.error(f"❌ 出错: {e}")
        return "喵？", 0, {"role": "assistant", "content": e}

#最抽象的ai输出函数
async def ask_deepseek(prompt, max_tokens=1024, temperature=0.5, response_format=None, timeout=60.0):
    # 构造请求体
    json_dic = {
        "model": "deepseek-chat", 
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens, 
        "temperature": temperature 
    }
    
    
    if response_format:
        json_dic["response_format"] = response_format

    try:
        async with httpx.AsyncClient() as client:
            # 发送请求
            response = await client.post(
                f"{config.DEEP_SEEK_BASE_URL}/chat/completions",
                json=json_dic,
                headers={"Authorization": f"Bearer {config.DEEP_SEEK_API_KEY}"},
                timeout=timeout
            )
            # logging.info("--- 发送给 DS 的完整数据 ---")
            # logging.info(json.dumps(json_dic, indent=2, ensure_ascii=False))
            # logging.info("---------------------------")
            # 检查状态码 
            response.raise_for_status() 
            
            # 返回JSON
            return response.json()

    except httpx.TimeoutException:
        logging.error("❌ DeepSeek 请求超时了")
        return None
    except Exception as e:
        logging.error(f"❌ 调用 DeepSeek 出错: {e}")
        return None
    

# async def ask_AI(messages, api_key, model_name = "moonshotai/Moonshot-v1-8k"):
#     """
#     通过硅基流动接入AI 
#     """
#     url = "https://api.siliconflow.cn/v1/chat/completions"

#     try:
#         async with httpx.AsyncClient() as client:
#             response = await client.post(
#                 url,
#                 json={
#                     "model": model_name, 
#                     "messages": messages,
#                     "response_format": {"type": "json_object"},
#                     "max_tokens": config.MAX_TOKEN, 
#                     "temperature": 0.7 
#                 },
#                 headers={
#                     "Authorization": f"Bearer {api_key}",
#                     "Content-Type": "application/json"
#                 },
#                 timeout=60.0
#             )
            
#             res_data = response.json()
            
#             if "choices" not in res_data:
#                 logging.info(f"⚠️ 接口返回异常: {res_data}")
#                 # --- 修改：异常返回也要多加一个 0 (Token) ---
#                 return ["Miku 走神了喵..."], 0, [], 0

#             raw_content = res_data['choices'][0]['message']['content']
            
#             # 解析 AI 返回的 JSON 结构
#             try:
#                 res_json = json.loads(raw_content)
#                 reply_text = res_json.get("reply", "喵？").strip()
#                 score_change = res_json.get("score", 0)
#                 new_feeling = res_json.get("feeling", "无")
#             except Exception as parse_e:
#                 logging.info(f"⚠️ JSON 解析失败: {parse_e}")
#                 reply_text = raw_content.strip()
#                 score_change = 0

#             # 按照你原有的逻辑进行分句处理
#             reply_text_list = reply_text.split(config.SEPARATOR)
#             reply_dic_list = []
#             for text in reply_text_list:
#                 if text.strip(): 
#                     reply_dic_list.append({"role": "assistant", "content": text})

#             # 记录 Token 消耗
#             usage = res_data.get("usage", {})
#             total_tokens = usage.get('total_tokens', 0) # 提取 total_tokens
            
#             logging.info(f"📊输出模型消耗: {total_tokens} tokens")
#             DM.update_tokens(total_tokens, model_type="output")
#             DM.data["felling"] = new_feeling
#             DM.save_data()
           
#             return reply_text_list, score_change, reply_dic_list, total_tokens

#     except Exception as e:
#         logging.info(f"❌ ask_AI 请求失败: {e}")
#         return ["Miku 脑袋乱乱的喵..."], 0, [], 0

#     except Exception as e:
#         logging.info(f"❌ 运行出错: {e}")
#         # 保持返回格式一致，防止主程序报错
#         err_msg = "大脑乱掉了喵..."
#         return [err_msg], 0, [{"role": "assistant", "content": str(e)}],0
    
async def ask_AI(messages, api_key, model_name=None):
    if model_name is None:
        model_name = getattr(config, 'DAW_AI_MODEL_NAME', 'gemini-3-flash-preview')

    url = "https://doubao.zwchat.cn/v1/chat/completions"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json={
                    "model": model_name, 
                    "messages": messages,
                    "response_format": {"type": "json_object"}, 
                    "max_tokens": config.MAX_TOKEN, 
                    "temperature": 0.7 
                },
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                timeout=60.0
            )
            
            res_data = response.json()
            if "choices" not in res_data:
                logging.warning(f"⚠️ 接口返回异常: {res_data}")
                return ["Miku 走神了喵..."], 0, [], 0, "无"

            raw_content = res_data['choices'][0]['message']['content'].strip()
            
            # --- 核心修复逻辑 ---
            reply_text = ""
            score_change = 0
            new_feeling = "无"

            try:
                # 清理 Markdown 代码块
                clean_content = re.sub(r'```json\s*|```', '', raw_content).strip()
                res_json = json.loads(clean_content)

                # 【关键修复】：判断 AI 返回的是不是列表
                if isinstance(res_json, list):
                    # 如果是列表，通常取第一个元素，或者把所有 reply 拼起来
                    logging.info("💡 检测到 AI 返回了列表格式 JSON，已自动提取首项")
                    res_json = res_json[0] if len(res_json) > 0 else {}

                reply_text = res_json.get("reply", "").strip()
                score_change = res_json.get("score", 0)
                new_feeling = res_json.get("feeling", "无")

            except Exception as parse_e:
                logging.warning(f"⚠️ JSON 解析逻辑触发兜底: {parse_e}")
                logging.info("原始输出:\n%s", response)
                # 如果解析完全失败，把原始内容当做回复
                reply_text = False
            
            # --- 后续处理 ---
            if not reply_text:
                reply_text = "喵？"

            # 切割发送列表
            reply_text_list = [r.strip() for r in reply_text.split(config.SEPARATOR) if r.strip()]
            # 构造上下文记录
            reply_dic_list = [{"role": "assistant", "content": reply_text}]

            # Token 记录
            usage = res_data.get("usage", {})
            total_tokens = usage.get('total_tokens', 0)
            
            print(f"📊 消耗: {total_tokens} tokens | 想法: {new_feeling}")
            
            # 更新全局状态
            DM.update_tokens(total_tokens, model_type="output")
            DM.data["feeling"] = new_feeling 
            DM.save_data()
            
            return reply_text_list, score_change, reply_dic_list, total_tokens, new_feeling

    except Exception as e:
        logging.error(f"❌ ask_AI 运行彻底崩溃: {e}")
        return [""], 0, [], 0, "无"
    
async def get_silicon_balance(api_key: str):
    """
    获取硅基流动的账户余额
    """
    url = "https://api.siliconflow.cn/v1/user/info"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            res_data = response.json()
            
            if res_data.get("code") == 20000:
                data = res_data.get("data", {})
                # totalBalance 是总余额（充值+赠送）
                total_balance = data.get("totalBalance", "0")
                return f"报告主人！咱家账户里还剩 {total_balance} 元喵~"
            else:
                return f"查询失败了，错误码：{res_data.get('code')}"
    except Exception as e:
        return f"查询余额时大脑短路了：{e}"
    
async def ask_silicon_smart(messages, api_key, model_name="Qwen/Qwen2.5-7B-Instruct"):
    """
    专供决策使用的 AI 函数：返回原始 API 响应字典，由主程序解析
    """
    url = "https://api.siliconflow.cn/v1/chat/completions"

    # 1. 确保 messages 是列表格式 (适配字符串输入)
    formatted_messages = messages if isinstance(messages, list) else [{"role": "user", "content": str(messages)}]

    json_dic = {
        "model": model_name,
        "messages": formatted_messages,
        "max_tokens": 512, # 决策专用，不需要太长
        "temperature": 0.7,
        "response_format": {"type": "json_object"} # 强制要求返回 JSON
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url, 
                json=json_dic,
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=60.0
            )
            res_data = response.json()

            # --- 调试打印：使用 formatted_messages 避免字符串索引错误 ---
            usage = res_data.get("usage", {})
            print(f"📊决策模型消耗: {usage.get('total_tokens')} tokens")


            # 统计 Token（可选）
            if "usage" in res_data:
                DM.update_tokens(res_data["usage"].get("total_tokens", 0),model_type="decision")

            # 直接返回整个字典给 main.py
            return res_data

    except Exception as e:
        logging.error(f"❌ ask_silicon_smart 运行崩溃: {e}")
        import traceback
        traceback.print_exc()
        return None # 返回 None 让 main.py 进入错误处理