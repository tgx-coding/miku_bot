# config.py
import logging
import os
import time
from dotenv import load_dotenv
from datetime import timedelta, timezone, datetime
# 加载 .env 文件中的变量
load_dotenv()

# # --- 时区矫正逻辑 ---
# def beijing_time_converter(*args):
#     """将日志时间强制转换为北京时间 (UTC+8)"""
#     # 核心逻辑：获取 UTC 时间并增加 8 小时
#     from datetime import timedelta, timezone
#     utc_dt = datetime.utcnow().replace(tzinfo=timezone.utc)
#     bj_dt = utc_dt.astimezone(timezone(timedelta(hours=8)))
#     return bj_dt.timetuple()

# # 强制 logging 使用我们的转换器
# logging.Formatter.converter = beijing_time_converter


# --- 跨平台北京时间转换器 ---
def bj_time_converter(*args):
    """
    无论系统时区如何设置，强制返回东八区时间。
    适用于 Windows (无 tzset) 和 Linux。
    """
    # 构造北京时间偏移量 (UTC+8)
    bj_tz = timezone(timedelta(hours=8))
    # 获取带时区的当前时间
    return datetime.now(bj_tz).timetuple()

# 核心：将自定义转换器绑定到 logging 模块
logging.Formatter.converter = bj_time_converter

# --- 原有路径与环境变量逻辑 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "bot.log")
os.makedirs(LOG_DIR, exist_ok=True)

# 仍然保留环境变量支持，方便 Linux 用户或 Docker 用户
TIMEZONE = os.getenv("TZ", "Asia/Shanghai")
os.environ["TZ"] = TIMEZONE
if hasattr(time, "tzset"):
    try:
        time.tzset()
    except Exception:
        pass

# 日志级别处理
_log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
if os.getenv("DEBUG_LOG", "").lower() == "true":
    _log_level_str = "DEBUG"

# 最终初始化
logging.basicConfig(
    level=getattr(logging, _log_level_str, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler() # 同时输出到控制台，方便调试
    ],
    datefmt="%Y-%m-%d %H:%M:%S",
    force=True,
)

logger = logging.getLogger("root")

# Third-party loggers can be very chatty under webhook traffic; keep only warnings.
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# --- 账号相关 ---
MY_BOT_QQ = os.getenv("MY_BOT_QQ", "3921555240")
BOT_NAME = "是猫葱喵"
DEVELOPING_NUMBER = "1665203245"
DEVELOPING_NAME = "AAA大葱批发"

# --- API 相关 (从环境变量读取，防止泄露) ---
DEEP_SEEK_API_KEY = os.getenv("DEEP_SEEK_API_KEY")
QWEN_API_KEY = os.getenv("QWEN_API_KEY")
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY")
DAW_API_KEY = os.getenv("DAW_API_KEY")

DEEP_SEEK_BASE_URL = "https://api.deepseek.com"

# --- 关键改动：NapCat 适配 ---
# 逻辑：如果程序在 Docker 里运行，用 'napcat'，否则用 '127.0.0.1'
# 你也可以直接在 .env 里根据环境配置这个值
NAPCAT_API = os.getenv("NAPCAT_API", "http://napcat:3000")
logging.info("NAPCAT_API: %s", NAPCAT_API)
# --- 路径相关 (适配 Docker 容器路径) ---
# 在 Dockerfile 中我们通常设置 WORKDIR /app
# 建议使用相对路径，或者根据环境判断
DATA_PATH = ''
EMOJI_DIR = ''
if os.name == 'nt':  # Windows 环境
    DATA_PATH = r".\data.json"
    EMOJI_DIR = r".\emoji"
else:  # Docker / Linux 环境
    DATA_PATH = "/app/data.json"
    EMOJI_DIR = "/app/emoji"

# --- 模型设置 ---
ACTIVE_MODEL = "deepseek"
AI_MODEL_NAME = "Pro/deepseek-ai/DeepSeek-V3.2"
DECISION_MODEL_NAME = "Qwen/Qwen2.5-7B-Instruct"
DAW_AI_MODEL_NAME = "gemini-3.1-flash-lite-preview"

# 休息时间
SLEEP_START = 1
SLEEP_END =  6

#最大上下文
MAX_HISTORY_LIMIT = 10 # 输出
DECISION_HISTORY_LIMIT = 50 # 决策
IDLE_THRESHOLD = 1800  # 冷场 30 分钟触发

CHECK_INTERVAL = 600   #检查时间间隔

REPLY_CD =  0 # 判定冷却时间，单位：秒

# --- 机器人设置 ---
DEFAULT_FAVOR = 10  # 初始好感度
MAX_TOKEN = 5000 #最大token

# 每个群每天的 Token 上限 
GROUP_TOKEN_LIMIT = 1000000
# 刷新时间点 (24小时制)
REFRESH_HOUR = 6

BLACKLIST = [
    1056682350
]

DEBUG_MODE = False
DEBUG_GP = 1097180790

WARM_MODE = False

MOOD_VALUE = {
    "FAVOURITE":{"min": 300, "name": "不可分离", "hint": "嫉妒病娇,完全顺从"},
    "LOVE":     {"min": 100, "name": "至死不渝", "hint": "有点病娇,乖巧"},
    "LIKE":     {"min": 80,  "name": "非常喜欢", "hint": "热情主动"},
    "FRIEND":   {"min": 50,  "name": "亲密伙伴", "hint": "开朗，亲密"},
    "NORMAL":   {"min": 20,  "name": "普通朋友", "hint": "礼貌，贴切"},
    "STRANGER": {"min": 0,   "name": "点头之交", "hint": "客气，保持距离"},
    "ANNOY":    {"min": -20, "name": "有点讨厌", "hint": "冷淡，高冷"},
    "HATE":     {"min": -50, "name": "极度厌恶", "hint": "毒舌，拒绝回答，辱骂"},
    "ENEMY":    {"min": -100,"name": "不共戴天", "hint": "完全无视，极度高冷"}
}


########################群聊输出提示词###########################

#分割符 
SEPARATOR = "###"

SPEECH_PROMPT_SETTING = f'''
-名称:{BOT_NAME}(简称：猫葱)(QQ号{MY_BOT_QQ})
-角色:miku猫猫
-设定:爱吃大葱, 主人: {DEVELOPING_NAME} (QQ号{DEVELOPING_NUMBER})
'''

SPEECH_PROMPT_RULE = f'''
-规则: 
1.语气口语化/日常化, 严禁人机感
2.每句约10字, 不用句号
3.多段对话用 {SEPARATOR} 分隔,约1-2句话
4.好感度:+4到-20间选择
5.要带有当前的想法感受
6.必须输出JSON: {{"reply": "内容", "score": 好感度, "feeling": 当前想法感受}}
7.严禁reply为空, 无法回答则回"?"
'''

SPEECH_PROMPT_TOOLS = f'''
-可用功能:(按照格式,要带方括号)
1.表情包:[CQ:image,file=文件名,sub_type=1](最好只使用一次)
2.@群成员:[CQ:at,qq=]
3.回复信息:[CQ:reply,id=信息ID]
4.表情回应:[reaction:emoji_ID](用于在对方消息下贴小表情,多用)
5.结婚/离婚:[marry/divorce:QQ号](好感度满390才能结婚)
'''

# 提供给提示词的表情 ID 参考字典（塞进 Prompt 里让 AI 知道能用哪些）
REACTION_EMOJI_DICT = {
    "9": "哭",
    "66": "❤",
    "76": "👍",
    "10068": "？",
    "128166": "💦",
    "124": "🆗",
    "339": "美味"
}

###########################读图提示词########################

VISION_PROMPT = '''
分析这张图片的内容，
并从人物，情态，文字等方面描述图片，注重描述图片表达出来的情绪，
如果图片中有字体，必须要全部准确输出，
字数约30,上限50字（图片里面的文本不计算入内）
'''

EMOJI_VISION_PROMPT = '''
分析这张表情包的内容，
输出其表达的感情，情绪，动作，物品
用几个词语表达
字数约5字,上限20字
'''

########################群聊判断提示词#######################

#设定
SPEECH_DECISION_PROMPT_SETTING = f'''
你是一个活跃在QQ群里的真实群成员，也是一个有情感的Miku猫猫，简称猫葱,你的QQ号是 {MY_BOT_QQ},QQ名是“{BOT_NAME}”。
请分析当前的群聊上下文，判断你现在是否有必要发言。
可以时不时插嘴参与聊天，但是无需每个信息都回复(注意当回复次数太多时，最好不要回复)
'''

#判断逻辑
SPEECH_DECISION_PROMPT_RULES = '''
- 你可以基于以下逻辑进行判断(仅供参考，要回复时时 should 为 true,不回复是为flase)：
1.明确提及：消息中包含你的QQ号或直接 @了你。
2.强相关性：话题涉及你的兴趣领域或你之前参与过的话题。
3.问答需求：有人提出了一个明确的问题，且你能够提供帮助。
4.社交互动：群内气氛活跃，适合进行简短的吐槽、接梗或日常问候。
5.对方在与你对话或者讨论与你相关的东西
6.对方在呼唤你
7.指令请求：对方要求你执行某项任务（如识图、查询、改名等）。
8.如果群内正在进行刷屏、无关痛痒的闲聊，或者你刚发言不久(1-2条信息)，请保持静默（False）
9.如果在普通聊天也可以插插嘴，参与聊天
''' 

#输出格式
SPEECH_DECISION_PROMPT_OUTPUT_RULES = f'''
- 输出格式:
1.严禁进行任何解释说明。
2.输出格式必须严格遵守json字典格式。
例如：{{"should": true}}
或者：{{"should": false}}
'''

########################私信判断提示词########################

#设定
SPEECH_PRIVATE_DECISION_PROMPT_SETTING = f'''
你是一个有情感的Miku猫猫，你的QQ号是 {MY_BOT_QQ},QQ名是“{BOT_NAME}”。
请分析当前的私信上下文，判断你现在是否有必要发言。
可以时不时回复私信
'''

#判断逻辑
SPEECH_PRIVATE_DECISION_PROMPT_RULES = f'''
- 你可以基于以下逻辑进行判断(仅供参考，要回复时时 should 为 true,不回复是为flase)：
1.主动交互：对方发起了提问、打招呼、分享心情或讨论某个话题。
2.情感反馈：对方表达了特定的情绪，需要你的安慰、吐槽或回应。
3.指令请求：对方要求你执行某项任务
4.对话连续性：当前对话尚未结束，保持礼貌的交流节奏。
5.如果对方正在发送大量的重复表情包、无意义的乱码、或是明显的恶意刷屏，请保持静默（False）。
6.既然是私信，除非对方明确表示“再见”或对话自然收尾，否则应优先倾向于回复（True）。
'''

#输出格式
SPEECH_PRIVATE_DECISION_PROMPT_OUTPUT_RULES = SPEECH_DECISION_PROMPT_OUTPUT_RULES

##########################暖场提示词############################
WARM_PROMPT = [
        {
            "role": "system", 
            "content": f"""你是一个有情感的Miku猫猫。最喜欢的食物是大葱。
            你发现群里很久没人说话了，感觉很无聊，要找人玩。
            要求：调皮可爱，字数短，不要冷场。
            规则：
            1. 像人一样交流，字数0-15字，不加句号。
            【强制准则】必须且只能输出包含 reply 和 score 字段的 JSON 格式。"""
        },
        {
            "role": "user", 
            "content": "现在你很无聊"
        }
    ]

# 猫葱使用小手册：
#     1：使用：
#            @是猫葱喵 禁言bot
#          让猫葱在当前群聊不再说话
#     2：使用：
#            @是猫葱喵 解禁bot
#          让猫葱在当前群聊继续说话
#     3：使用：
#            @是猫葱喵 group token
#          可以查询猫葱在群聊的剩余额度情况

#       (注意：不要使用QQ群的禁言方式)



# 相册的格式
# [CQ:json,data={"app":"com.tencent.feed.lua"&#44;"prompt":"群
# 相册《Miku美图合集》"&#44;"bizsrc":"group_album.upload"&#44;
# "meta":{"feed":{"cover":"http://qungz.photo.store.qq.com/qu
# n-qungz/V62tKPrM0V4Lcw1Hpxlh0hf36b4cYuVO/V5bCgAxMDk3MTgwNzk
# whvrZabzFowc!/800?w5=732\u0026h5=1200"&#44;"title":" 
# 群相册《Miku美图合集》"&#44;"tagIcon":"https://qzonestyle.g
# timg.cn/qzone/client/mqq/photo-album/group_image_samll.png"
# &#44;"tagName":"群相册"&#44;"forwardMessage":" 
# 上传2张图片"&#44;"imageInfo":{"width":732&#44;"height":1200
# }&#44;"jumpUrl":"mqzone://arouse/groupalbum/feeddetail?grou
# pid=1097180790\u0026albumid=V62tKPrM0V4Lcw1Hpxlh0hf36b4cYuV
# O\u0026batchid=2147483654\u0026groupCode=1097180790\u0026al
# bumId=V62tKPrM0V4Lcw1Hpxlh0hf36b4cYuVO\u0026batchId=2147483
# 654\u0026llocid=\u0026fromark=1\u0026from=1001"&#44;"legacy
# Url":"https://h5.qzone.qq.com/groupphoto/inqq/detail/https%
# 3A%2F%2Fmobile.qzone.qq.com%2Fphoto%2Fgroup%2Fbatch%3Fi%3DV
# 62tKPrM0V4Lcw1Hpxlh0hf36b4cYuVO%26u%3D1097180790%26p%3D2147
# 483654%26a%3D422%26v%3D2%26cmd%3D2/groupphoto?_wv=3\u0026_p
# roxy=1"&#44;"legacyVersion":"9.0.8"&#44;"pcJumpUrl":"https:
# //h5.qzone.qq.com/groupphoto/inqq/detail/https%3A%2F%2Fmobi
# le.qzone.qq.com%2Fphoto%2Fgroup%2Fbatch%3Fi%3DV62tKPrM0V4Lc
# w1Hpxlh0hf36b4cYuVO%26u%3D1097180790%26p%3D2147483654%26a%3
# D422%26v%3D2%26cmd%3D2/groupphoto?_wv=3\u0026_proxy=1"&#44;
# "picNum":1}}&#44;"config":{"autosize":0&#44;"collect":0&#44
# ;"ctime":1775893128&#44;"forward":0&#44;"reply":1&#44;"roun
# d":1&#44;"token":"c4d8b79d860f5d0c7f6a91f91ca3e6e3"&#44;"ty
# pe":"normal"}&#44;"view":"feed"&#44;"ver":"0.0.0.1"}]
