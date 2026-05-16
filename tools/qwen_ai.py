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



