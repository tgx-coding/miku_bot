import os
import json
import logging
import config
import numpy as np
import time
import shutil  
from datetime import datetime

class DataManager:
    def __init__(self):
        self.data_path = config.DATA_PATH
        # 定义备份路径
        self.bak_path = self.data_path + ".bak"
        self.start_data = {
            "Favorability": {},
            "output_token_count": {"all_tokens": 0, "times": 0},
            "decision_token_count": {"all_tokens": 0, "times": 0},
            "last_msg_time" : {},
            "feeling" : "无",
            "image_cache": {},
            "chat_contexts" : {},
            "user_infor" : {},
            "marry_list" : []

        }
        self.data = self.start_data.copy() # 初始化内存数据
        self.load_data()
    
    def load_data(self):
        """加载数据：多级保护逻辑"""
        # 1. 尝试从主路径加载
        if self._attempt_load(self.data_path):
            return

        # 2. 如果主路径失败，尝试从备份加载
        logging.warning(f"⚠️ 主存档损坏或不存在，尝试读取备份: {self.bak_path}")
        if os.path.exists(self.bak_path):
            if self._attempt_load(self.bak_path):
                logging.info("♻️ 成功从备份文件恢复数据！")
                # 立即尝试修复主文件
                self.save_data()
                return

        # 3. 万不得已，初始化
        self.data = self.start_data.copy()
        if not os.path.exists(self.data_path):
            logging.info("🆕 未找到存档，已初始化新存档")
            self.save_data()
        else:
            logging.warning("🚨 警告：所有存档均损坏！数据已重置。")

    def _attempt_load(self, path):
        """内部读取逻辑，增加损坏现场保存"""
        if not os.path.exists(path):
            return False
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    raise ValueError("空文件")
                new_data = json.loads(content)
                # 使用合并更新，确保新添加的字段不会丢失
                self.data = self.start_data | new_data
                return True
        except (json.JSONDecodeError, ValueError) as e:
            # 记录灾难现场：重命名损坏的文件，防止被 save_data 覆盖
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            corrupt_path = f"{path}_corrupted_{timestamp}.json"
            try:
                os.rename(path, corrupt_path)
                logging.info(f"📁 已将损坏文件移至: {corrupt_path}")
            except:
                pass
            return False

    def save_data(self):
        """保存数据：原子化写入 + 自动备份"""
        temp_path = self.data_path + ".tmp"
        try:
            # 1. 先写临时文件
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
            
            # 2. 确保临时文件写入磁盘 (强制同步)
            os.replace(temp_path, self.data_path)
            
            # 3. 异步备份：将当前成功的存档存为 .bak
            shutil.copy2(self.data_path, self.bak_path)
            
            # logging.info("💾 存档已安全更新并备份")
        except Exception as e:
            logging.error(f"❌ 写入极端失败: {e}")
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def add_favor(self, user_id, num=0):
        """好感度修改"""
        uid = str(user_id)
        # 1. 确保用户存在，初始值 10
        if uid not in self.data["Favorability"]:
            self.data["Favorability"][uid] = 10
        
        # 2. 限制单次变动幅度 (比如单次最多加3分，最少扣10分)
        # 注意：这里必须转为 int()，否则 save_data 会报错
        change = int(np.clip(num, -10, 3))
        
        # 3. 计算新总分，并建议对总分也做个范围限制（比如 0 到 1000）
        current_score = self.data["Favorability"][uid]
        total_score = int(current_score + change)
        
        self.data["Favorability"][uid] = total_score
        
        # 4. 自动存档并打印
        self.save_data() 
        #logging.info(f'❤ 用户 {user_id} 好感度变动: {change}, 当前总计: {total_score}')
        
        return total_score
    
    def get_favor(self, user_id):
        """好感度查询"""
        uid = str(user_id)
        # 如果找不到，返回默认值 10
        return self.data["Favorability"].get(uid, 10)
    
    def get_favor_msg(self, user_id):
        """根据好感度数值返回对应的评价话术"""
        score = self.get_favor(user_id)
        
        # 从 config 导入配置（或者直接写在方法里）
        
        
        # 找到第一个符合条件的区间（从高到低找）
        for level in config.FAVOR_LEVELS:
            if score >= level["min"]:
                return f"{level['msg']}"
        
        return f""
    
            
    def get_level_data(self, user_id):
        """根据好感度获取完整的情绪数据对象"""
        score = self.get_favor(user_id)
        
        # 按分值从高到低排序搜索
        sorted_levels = sorted(config.MOOD_VALUE.values(), key=lambda x: x['min'], reverse=True)
        
        for level in sorted_levels:
            if score >= level["min"]:
                # ✅ 修复：创建一个副本，并把当前的真实分数(favor)塞进去
                result = level.copy()
                result["favor"] = score 
                return result
        
        # ✅ 修复：保底情况也必须返回字典格式
        default_level = sorted_levels[-1].copy()
        default_level["favor"] = score
        return default_level
    


    def get_emoji_list(self,path=r"./emoji/"):
        """
        扫描指定目录，获取所有图片文件名列表
        支持 .jpg, .png, .gif, .jpeg, .webp
        """
        if not os.path.exists(path):
                os.makedirs(path)
                return []

        # 定义图片后缀白名单
        valid_extensions = ('.jpg', '.png', '.gif', '.jpeg', '.webp')
        
        clean_names = []
        
        for f in os.listdir(path):
            # 拼接完整路径判断是否是文件
            full_path = os.path.join(path, f)
            
            if os.path.isfile(full_path):
                # 分离文件名和扩展名

                name, ext = os.path.splitext(f)
                
                # 3只有在白名单内的图片才添加
                if ext.lower() in valid_extensions:
                        clean_names.append(name)
                        
        return clean_names

    def update_tokens(self, total_tokens: int, model_type: str = "output", group_id=None):
        """
        累计计算 Token 消耗
        :param total_tokens: 本次消耗的 token 数
        :param model_type: 模型类型 'output' 或 'decision'
        :param group_id: 群号，默认为 None (私聊时不传)
        """
        # 1. 映射模型层级统计
        key = f"{model_type}_token_count"
        if key not in self.data:
            self.data[key] = {"all_tokens": 0, "times": 0}
        
        if total_tokens > 0:
            # 模型全局累加
            self.data[key]["all_tokens"] += total_tokens
            self.data[key]["times"] += 1
            
            # 2. 重点：处理群聊相关的统计
            if group_id:
                gid_str = str(group_id)
                
                # A. 每日额度统计 (会被 worker 清空)
                if "group_token_usage" not in self.data:
                    self.data["group_token_usage"] = {}
                self.data["group_token_usage"][gid_str] = self.data["group_token_usage"].get(gid_str, 0) + total_tokens
                
                # B. 永久总量统计 (永远不被清空)
                if "total_group_usage" not in self.data:
                    self.data["total_group_usage"] = {}
                self.data["total_group_usage"][gid_str] = self.data["total_group_usage"].get(gid_str, 0) + total_tokens

            # 打印一下调试信息
            all_t = self.data[key]["all_tokens"]
            times = self.data[key]["times"]
            logging.debug(f"📊 [{model_type.upper()}] 更新: 本次 {total_tokens}, 总计 {all_t}, 平均 {all_t/times:.2f}")
            
            # 3. 自动保存
            self.save_data()

    def recount_tokens (self, model_type: str):
        key = f"{model_type}_token_count"
        if key not in self.data:
            self.data[key] = {"all_tokens": 0, "times": 0}

        self.data[key]["all_tokens"] = 0
        self.data[key]["times"] = 0

        self.save_data()
        logging.debug(f"📊 [{model_type.upper()}] 已清空总 {model_type} token消耗")


    def clean_old_cache(self, max_days=7):
        """清理过期缓存，并自动剔除不符合新字典格式的旧数据"""
        current_time = time.time()
        expiry_seconds = max_days * 86400
        
        removed_count = 0
        malformed_count = 0 # 统计格式错误的
        
        # 获取缓存字典的副本进行遍历
        cache_items = list(self.data.get("image_cache", {}).items())
        
        for img_id, info in cache_items:
            should_delete = False
            reason = ""

            # --- 1. 检查是否符合新格式 {"path": "...", "last_time": ...} ---
            if not isinstance(info, dict):
                should_delete = True
                malformed_count += 1
                reason = "格式老旧"
            else:
                # --- 2. 格式正确，检查是否过期 ---
                last_time = info.get("last_time", 0)
                if current_time - last_time > expiry_seconds:
                    should_delete = True
                    reason = "已过期"

            # 执行删除逻辑
            if should_delete:
                # 尝试物理删除文件
                file_path = info.get("path") if isinstance(info, dict) else info
                if file_path and os.path.exists(str(file_path)):
                    try:
                        os.remove(str(file_path))
                    except Exception as e:
                        logging.error(f"❌ 物理文件删除失败 ({file_path}): {e}")
                
                # 从内存中剔除
                del self.data["image_cache"][img_id]
                removed_count += 1
                # logging.info(f"🗑️ 已清理条目 {img_id}，原因: {reason}")

        if removed_count > 0:
            self.save_data()
            logging.info(f"🧹 大扫除完成！")
            logging.info(f"   - 共清理条目: {removed_count} 个")
            logging.info(f"   - 其中旧格式数据: {malformed_count} 个")
    
    def get_involved_users_info(self, segment):
        """从对话片段中提取提到的QQ及其对应的旧信息"""
        import re
        qq_ids = set()
        for msg in segment:
            # 匹配你 format_user_message 里的 [用户:12345] 格式
            found = re.findall(r"用户:(\d+)", msg["content"])
            qq_ids.update(found)
        
        # 从 data["user_infor"] 获取这些人已有的记录
        all_info = self.data.get("user_infor", {})
        return {uid: all_info.get(uid, []) for uid in qq_ids}

    def save_extracted_info(self, extracted_dict):
        """将 AI 提取的 {"QQ": "信息"} 存入 data["user_infor"]"""
        if "user_infor" not in self.data:
            self.data["user_infor"] = {}
        
        for uid, info in extracted_dict.items():
            uid_str = str(uid)
            if uid_str not in self.data["user_infor"]:
                self.data["user_infor"][uid_str] = []
            # 去重保存
            if info not in self.data["user_infor"][uid_str]:
                self.data["user_infor"][uid_str].append(info)
        self.save_data()

    def get_compact_status_and_archive(self, qqs):  
        """
        在 DM 内部组装成员状态表与档案，增加【身份】标识
        """
        status_rows = []
        archive_parts = []
        
        # 1. 获取结婚名单 (确保是列表且元素为字符串)
        marry_list = [str(q) for q in self.data.get("marry_list", [])]
        
        for qq in qqs:
            qq_str = str(qq)
            
            # 2. 获取好感度等实时数据
            level = self.get_level_data(qq_str)
            
            # 类型校验：防止 level 数据异常导致崩溃
            if not isinstance(level, dict):
                logging.warning(f"⚠️ 警告: QQ {qq_str} 数据格式错误，已重置显示。")
                level = {'name': '未知', 'favor': 0, 'mood': '稳定'}

            # --- 核心逻辑：判断身份 ---
            # 如果在结婚名单里，身份就是“情侣”，否则是“成员”
            identity = "情侣" if qq_str in marry_list else "成员"

            # 3. 组装极致压缩格式: [QQ|名|身份|好感|情绪]
            name = level.get('name', '未知')
            favor = level.get('favor', 0)
            mood = level.get('mood', '稳定')
            
            status_rows.append(f"[{qq_str}|{name}|{identity}|{favor}|{mood}]")
            
            # 4. 获取档案
            info = self.data.get("user_infor", {}).get(qq_str, "新面孔")
            archive_parts.append(f"ID({qq_str}):{info}")
        
        # 组装带标题的最终文本，方便 AI 直接阅读
        status_table = "[活跃成员状态: QQ|名称|身份|好感|情绪]\n" + "\n".join(status_rows)
        archive_section = "[成员档案库]\n" + "\n".join(archive_parts)
        
        return status_table, archive_section
    
    def marry(self, qq: str):
        """处理结婚逻辑"""
        if "marry_list" not in self.data:
            self.data["marry_list"] = []
        
        if qq not in self.data["marry_list"]:
            self.data["marry_list"].append(str(qq))
            self.save_data() # 记得加括号执行
            return True
        return False

    def divorce(self, qq: str):
        """处理离婚逻辑"""
        if "marry_list" in self.data and str(qq) in self.data["marry_list"]:
            self.data["marry_list"].remove(str(qq))
            self.save_data()
            return True
        return False

    def is_married(self, qq: str):
        """查询是否已婚"""
        return str(qq) in self.data.get("marry_list", [])

DM = DataManager()