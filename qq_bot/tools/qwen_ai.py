import httpx
import json
import logging

# 配置日志，方便调试
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("QwenAI")
TEXT_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
VISION_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"



async def ask_chat(messages: list, api_key: str, model: str = "qwen-plus"):
    """
    1. 基础多轮对话调用 (带 Miku 性格)
    :param messages: 符合 OpenAI 格式的消息列表 [{"role": "system", "content": "..."}, ...]
    :param api_key: 阿里云 DashScope API Key
    :param model: 默认使用 qwen-plus (性价比最高)
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "input": {
            "messages": messages
        },
        "parameters": {
            "result_format": "message",
            "temperature": 0.8,
            "max_tokens": 512
        }
    }

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(TEXT_URL, headers=headers, json=payload, timeout=20)
            res_json = resp.json()
            
            if "output" in res_json:
                content = res_json["output"]["choices"][0]["message"]["content"]
                # 尝试解析 JSON (因为你的 Miku 协议要求输出 JSON)
                try:
                    return json.loads(content)
                except:
                    return content # 如果 AI 没按格式出，返回原始文本
            else:
                logger.error(f"Qwen API 报错: {res_json}")
                return None
        except Exception as e:
            logger.error(f"网络请求失败: {e}")
            return None

async def ask_vision(prompt: str, img_url: str, api_key: str, model: str = "qwen-vl-plus"):
    """
    2. 视觉识图调用
    :param prompt: 对图片的指令 (例如: '描述一下这张图')
    :param img_url: 图片的公网直链 (NapCat 提供的 URL)
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"image": img_url},
                        {"text": prompt}
                    ]
                }
            ]
        },
        "parameters": {
            "result_format": "message"
        }
    }

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(VISION_URL, headers=headers, json=payload, timeout=30)
            res_json = resp.json()
            
            if "output" in res_json:
                return res_json["output"]["choices"][0]["message"]["content"][0]["text"]
            else:
                logger.error(f"Qwen-VL 报错: {res_json}")
                return "呜...人家的眼睛好像进沙子了喵。"
        except Exception as e:
            logger.error(f"视觉请求失败: {e}")
            return "网络坏掉了，看不见大葱在哪里喵！"

async def ask_decision(prompt: str, api_key: str):
    """
    3. 专门用于 should 判断的轻量级调用
    使用 qwen-turbo 以节省成本
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "qwen-turbo",
        "input": {
            "messages": [
                {"role": "user", "content": prompt}
            ]
        },
        "parameters": {
            "result_format": "message",
            "response_format": {"type": "json_object"} # 强制 JSON 输出
        }
    }

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(TEXT_URL, headers=headers, json=payload, timeout=10)
            res_json = resp.json()
            content = res_json["output"]["choices"][0]["message"]["content"]
            return json.loads(content)
        except:
            return {"should": False} # 出错默认不回复
        
