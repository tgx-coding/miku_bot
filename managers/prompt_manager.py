import config
from managers.data_manager import DM

class PromptManager:
    """
    提示词合成管理器
    负责将离散的配置项、用户状态和聊天记录合成为完整的 Prompt
    """

    @staticmethod
    def get_vision_prompt(is_emoji=False) -> str:
        """
        获取读图提示词
        :param is_emoji: 是否为表情包
        """
        return config.EMOJI_VISION_PROMPT if is_emoji else config.VISION_PROMPT

    @staticmethod
    def build_decision_prompt(message_type: str, history_msgs: list, sender_id: str, current_msg: str) -> str:
        """
        合成决策层提示词（判断是否需要回复）
        :param message_type: "group" 或 "private"
        :param history_msgs: 当前的上下文历史列表
        :param sender_id: 发送者QQ
        :param current_msg: 当前解析后的消息
        """
        # 根据群聊/私信选择对应的提示词组件
        if message_type == "private":
            setting = config.SPEECH_PRIVATE_DECISION_PROMPT_SETTING
            rules = config.SPEECH_PRIVATE_DECISION_PROMPT_RULES
            output_rules = config.SPEECH_PRIVATE_DECISION_PROMPT_OUTPUT_RULES
        else:
            setting = config.SPEECH_DECISION_PROMPT_SETTING
            rules = config.SPEECH_DECISION_PROMPT_RULES
            output_rules = config.SPEECH_DECISION_PROMPT_OUTPUT_RULES

        # 提取历史记录文本
        history_text = "\n".join([f"{m['role']}: {m['content']}" for m in history_msgs]) if history_msgs else "暂无历史记录"

        # 组合完整提示词
        full_prompt = (
            f"{setting}\n"
            f"{rules}\n"
            f"{output_rules}\n"
            f"--- 最近对话历史 ---\n"
            f"{history_text}\n"
            f"--- 当前新消息 ---\n"
            f"用户({sender_id})说: {current_msg}\n"
            f"请判断你是否需要回复（should: True/False）。"
        )
        return full_prompt

    @staticmethod
    def build_chat_system_prompt(emoji_list: list, feeling: str = "无", involved_users_info: str = "",status_table :str= '') -> str:       
        """
        合成输出层（聊天层）的 System Prompt
        包含核心设定、规则、可用工具以及当前加载的表情包
        """
        str_emoji_list = ''
        for name in emoji_list:
            str_emoji_list += name + ","
        # logging.debug("emoji list:",str_emoji_list)
        # felling = DM.data.get("felling","无")
        # logging.debug("当前想法：",felling)
        prompt = (
            f"{config.SPEECH_PROMPT_SETTING}"#设定
            f"{config.SPEECH_PROMPT_RULE}"#规则
            f"{config.SPEECH_PROMPT_TOOLS}"#工具
            f"当前感受和想法:{feeling}"
            f"{status_table}" # 插入状态表
            # f"最近对话成员的档案"
            # f"{involved_users_info if involved_users_info else '暂无详细档案'}"
            f"- 表情包列表：{str_emoji_list}"
        )
        return prompt

    @staticmethod
    def format_user_message(sender_id, user_input):
        """
        【极致压缩版】不再包含好感度和情绪，只保留 ID 和内容
        """
        # 甚至可以去掉 "消息ID" 这几个字，直接用 ID:
        return f"用户:{sender_id} 说: {user_input}"
    
    @staticmethod
    def build_info_extraction_prompt(chat_segment: list, existing_info: dict) -> str:
        history_text = "\n".join([f"{m['role']}: {m['content']}" for m in chat_segment])
        info_text = "\n".join([f"QQ[{k}]已有信息: {v}" for k, v in existing_info.items()])

        prompt = (
            "你是一个观察细致的助手。请分析以下对话，提取其中群成员的新人设、爱好或特征。\n"
            "1. 只提取确定的事实，用户的爱好，性格，等信息，不提取猜测。\n"
            "2. 必须输出 JSON 格式: {\"QQ号\": \"提取的一句话新信息\"}。\n"
            "3. 如果没发现新信息，返回 {}。"
            "【已知信息】(请勿重复提取):\n"
            f"{info_text}\n\n"
            "【最近对话】:\n"
            f"{history_text}\n\n"
        )
        return prompt

    @staticmethod
    def build_status_table(involved_users_data, marry_list=None):
        """
        生成活跃成员状态表
        involved_users_data 格式: { "QQ号": {"name": "名称", "favor": 100, "mood": "情绪"} }
        marry_list 格式: ["QQ号1", "QQ号2"]
        """
        if not involved_users_data:
            return ""
        
        # 确保 marry_list 是列表，防止 None 报错
        if marry_list is None:
            marry_list = []
        
        header = "\n[活跃成员状态: 用户|名称|身份|好感|情绪]\n"
        rows = []
        for qq, info in involved_users_data.items():
            name = info.get("name", "未知")
            favor = info.get("favor", 0)
            mood = info.get("mood", "稳定")
            
            # 如果该 QQ 在结婚名单里，标记为“情侣”，否则为空
            identity = "情侣" if str(qq) in marry_list else "成员"
            
            # 将身份加入表格行中
            rows.append(f"[{qq}|{name}|{identity}|{favor}|{mood}]")
        
        return header + "\n".join(rows)
# 实例化一个单例供外部直接调用
PM = PromptManager()