import os
import re
import json
import time
import asyncio
import random
from typing import Dict, Any
from pathlib import Path
from astrbot.api.star import Context, Star, register
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.core.star.filter.event_message_type import EventMessageType
from astrbot.api.star import StarTools
from astrbot.api import logger
from .utils.ai_handler import generate_quiz, generate_snarky_eval
from .utils.db_handler import DatabaseHandler
@register(
    "astrbot_plugin_orangequiz",
    "largefox",
    "让bot化身性格鉴定师！LLM自动生成互动问卷，智能分析结果，测完还送一张属性海报。",
    "1.0.1",
    "",
)
class OrangeQuiz(Star):
    async def terminate(self):
        if getattr(self, "_cleanup_task", None):
            self._cleanup_task.cancel()

    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        self.config = config or {}
        self.sessions: Dict[str, Any] = {}
        self.create_sessions: Dict[str, Any] = {}
        self._initialized = False
        self._init_lock = asyncio.Lock()

        try:
            self.base_data_dir = StarTools.get_data_dir()
        except Exception as e:
            logger.error(
                f"OrangeQuiz: StarTools.get_data_dir() failed, using fallback path. Error: {e}"
            )
            self.base_data_dir = Path(
                os.path.abspath(
                    os.path.join(
                        os.getcwd(), "data", "plugin_data", "astrbot_plugin_orangequiz"
                    )
                )
            )

        self.quizzes_dir = self.base_data_dir / "quizzes"
        self.temp_dir = self.base_data_dir / "temp"

        for d in [self.quizzes_dir, self.temp_dir]:
            os.makedirs(d, exist_ok=True)

        # Generate default quiz if not exists
        default_quiz_path = self.quizzes_dir / "000001.json"
        if not os.path.exists(default_quiz_path):

            default_quiz = {
                "id": "000001",
                "title": "你对可爱狐狐的接受程度测试",
                "category": "狐狸控纯度鉴定",
                "type": "score",
                "questions": [
                    {
                        "text": "如果有一天，一只毛茸茸的橙色小狐狸在路边可怜巴巴地冲你叫，你会怎么做？",
                        "options": [
                            {
                                "label": "A",
                                "text": "带它回家，给它买最好的肉，把它当祖宗供起来，天天给它梳毛！",
                                "weights": {"总分": 10},
                            },
                            {
                                "label": "B",
                                "text": "摸摸头，喂点吃的，然后帮它找收容所，或者发朋友圈找领养。",
                                "weights": {"总分": 5},
                            },
                            {
                                "label": "C",
                                "text": "看一眼，觉得可爱，但不打算管，转身走人。",
                                "weights": {"总分": 1},
                            },
                            {
                                "label": "D",
                                "text": "狐狸？不管，这玩意儿身上可能有寄生虫或者是保护动物，报警处理。",
                                "weights": {"总分": 0},
                            },
                        ],
                    }
                ],
                "results_logic": {
                    "总分": {
                        "name": "综合评级",
                        "ranges": [
                            {
                                "min": 0,
                                "max": 1,
                                "name": "铁石心肠",
                                "desc": "你的心里只有冷酷的现实，完全免疫可爱的狐狐攻势。建议多看看动物纪录片培养感情。",
                            },
                            {
                                "min": 2,
                                "max": 5,
                                "name": "理智欣赏者",
                                "desc": "你觉得狐狐很可爱，但依然能保持清醒的理智，不会轻易被毛茸茸的美色迷惑。",
                            },
                            {
                                "min": 6,
                                "max": 10,
                                "name": "超级骨灰级狐狸控",
                                "desc": "承认吧，你根本拒绝不了毛茸茸的大尾巴！你完全就是个狐狸控，恨不得把全世界的可爱狐狐都带回家吸爆！",
                            },
                        ],
                    }
                },
            }
            try:
                with open(default_quiz_path, "w", encoding="utf-8") as f:
                    json.dump(default_quiz, f, ensure_ascii=False, indent=4)
            except Exception as e:
                logger.error("Failed to write default quiz.", exc_info=e)

    async def _ensure_init(self):
        """Lazy async initialization guarded by a lock to prevent concurrent double-init."""
        if self._initialized:
            return
        async with self._init_lock:
            # Double-check after acquiring the lock
            if self._initialized:
                return
            self.db = DatabaseHandler(str(self.base_data_dir))
            await self.db.init_db()
            if getattr(self, "_cleanup_task", None):
                self._cleanup_task.cancel()
            self._cleanup_task = asyncio.create_task(self._temp_cleanup_loop())
            self._initialized = True

    async def _temp_cleanup_loop(self):
        """Runs periodically to clean up temporary HTML and image files, and expired sessions."""
        while True:
            try:
                current_time = time.time()
                if os.path.exists(self.temp_dir):
                    for filename in os.listdir(self.temp_dir):
                        filepath = self.temp_dir / filename
                        if os.path.isfile(filepath):
                            # Clean up files older than 1 hour
                            if current_time - os.path.getmtime(filepath) > 3600:
                                os.remove(filepath)

                # Clean up expired sessions (1 hour timeout)
                for map_dict in [self.sessions, self.create_sessions]:
                    expired_keys = [
                        k
                        for k, v in map_dict.items()
                        if current_time - v.get("last_active", current_time) > 3600
                    ]
                    for k in expired_keys:
                        del map_dict[k]
            except Exception as e:
                logger.error(f"OrangeQuiz cleanup loop error: {e}", exc_info=True)
            # Wait for 1 hour before next cleanup
            await asyncio.sleep(3600)

    def get_prefix(self) -> str:
        try:
            cfg = self.context.get_config()
            prefixes = cfg.get("wake_prefix", ["/"])
            if prefixes and isinstance(prefixes, list) and len(prefixes) > 0:
                return prefixes[0]
            elif isinstance(prefixes, str) and prefixes:
                return prefixes
        except Exception as e:
            logger.error(f"Failed to fetch wake_prefix configuration: {e}")
        return "/"

    def _is_admin(self, user_id: str) -> bool:
        try:
            admins = self.context.get_config().get("admins_id", [])
            return str(user_id) in [str(a) for a in admins]
        except Exception as e:
            logger.error(f"OrangeQuiz error: {e}")
            return False

    async def _get_persona_prompt(self, event: AstrMessageEvent) -> str:
        try:
            conv_mgr = self.context.conversation_manager
            curr_cid = await conv_mgr.get_curr_conversation_id(event.unified_msg_origin)
            conversation = await conv_mgr.get_conversation(
                event.unified_msg_origin, curr_cid
            )
            if conversation and conversation.persona_id:
                persona = self.context.persona_manager.get_persona(
                    conversation.persona_id
                )
                if persona:
                    prompt_val = getattr(
                        persona,
                        "system_prompt",
                        getattr(
                            persona,
                            "prompt",
                            getattr(persona, "description", getattr(persona, "bot_info", "")),
                        ),
                    )
                    if prompt_val and isinstance(prompt_val, str):
                        return prompt_val
                    return ""
        except Exception as e:
            logger.error(f"Failed to fetch persona profile: {e}")
        return ""

    def _load_quiz(self, test_id: str) -> Dict:
        filepath = self.quizzes_dir / f"{test_id}.json"
        if not os.path.exists(filepath):
            return None
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"OrangeQuiz error: {e}")
            return None

    @filter.command("quiz_list", alias=["测试列表", "问卷列表"], priority=1)
    async def quiz_list(self, event: AstrMessageEvent, page: int = 1):
        event.stop_event()
        files = [f for f in os.listdir(self.quizzes_dir) if f.endswith(".json")]
        if not files:
            yield event.plain_result("当前没有任何可用的问卷！")
            return

        files.sort()
        per_page = 10
        total_pages = max(1, (len(files) + per_page - 1) // per_page)
        
        if page < 1:
            page = 1
        elif page > total_pages:
            page = total_pages
            
        start_idx = (page - 1) * per_page
        page_files = files[start_idx:start_idx+per_page]

        reply = f"=== 可用问卷列表 (第 {page}/{total_pages} 页) ===\n"
        loaded = 0
        for file in page_files:
            try:
                with open(self.quizzes_dir / file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    author_postfix = f" (作者: {data.get('author', '未知')})"
                    reply += f"- {data.get('test_id')} : {data.get('title')}{author_postfix}\n"
                    loaded += 1
            except Exception as e:
                logger.warning(f"OrangeQuiz: Failed to load quiz file {file}: {e}")
                continue

        if loaded > 0:
            if total_pages > 1:
                reply += f"\n使用 {self.get_prefix()}quiz_list [页码] 进行翻页。"
            reply += f"\n使用 {self.get_prefix()}quiz [ID] 开始答题。"
            yield event.plain_result(reply)
        else:
            yield event.plain_result("这里空空如也，并没有任何可用的测试问卷呢...")

    @filter.command("quiz_hot", alias=["热门测试", "测试排名"], priority=1)
    async def quiz_hot(self, event: AstrMessageEvent):
        event.stop_event()
        hot_list = await self.db.get_hot_quizzes(5)
        if not hot_list:
            yield event.plain_result("目前还没有人完成过任何问卷测试！快去争夺第一吧！")
            return

        reply = "🔥 【OrangeQuiz 热榜 Top 5】 🔥\n\n"
        for idx, item in enumerate(hot_list):
            test_id = item["test_id"]
            cnt = item["play_count"]

            # 查一下本地能对应的标题
            quiz_data = self._load_quiz(test_id)
            title = (
                quiz_data.get("title", "未知已下线问卷")
                if quiz_data
                else "未知已下线问卷"
            )

            reply += f"Top {idx + 1}. {title} (ID: {test_id}) - {cnt}次\n"

        yield event.plain_result(reply)

    @filter.command("quiz_create", alias=["创建测试", "新增问卷", "出题"], priority=1)
    async def quiz_create(self, event: AstrMessageEvent):
        event.stop_event()
        user_id = event.get_sender_id()

        await self._ensure_init()

        is_group = "group" in event.unified_msg_origin.lower()
        if is_group:
            val = self.config.get("allow_group_create", False)
            allow_group_create = str(val).lower() != "false"
            if not allow_group_create:
                yield event.plain_result(
                    f"🚫 防刷屏保护已开启：不支持在群聊内创建新问卷。\n👉 请前往与机器人的【私聊】窗口发送 {self.get_prefix()}quiz_create 创建测试！"
                )
                return

        if not self._is_admin(user_id):
            if self.config.get("admin_only_create", False):
                yield event.plain_result(
                    "🚫 当前系统已开启「仅管理员可创建新问卷」模式，您暂时没有权限使用此功能。"
                )
                return

            limit = int(self.config.get("daily_create_limit", 3))
            created = await self.db.get_daily_create_count(user_id)
            if created >= limit:
                yield event.plain_result(
                    f"⚠️ 您今天已经生成过 {created} 份问卷了，超出了每日 {limit} 次的限制，请明天再来吧！"
                )
                return

        session_key = f"{event.unified_msg_origin}_{user_id}"
        if session_key in self.create_sessions:
            del self.create_sessions[session_key]

        self.create_sessions[session_key] = {
            "step": "AWAITING_TITLE",
            "mod_count": 0,
            "last_active": time.time(),
        }
        yield event.plain_result(
            "Tips: 接下来你可以随时回复“取消”退出操作。\n\n首先，你想创建一个什么问卷呢？请先为它起一个响亮的标题吧："
        )

    @filter.command("quiz", alias=["测试", "做题", "答题"], priority=1)
    async def quiz_cmd(
        self, event: AstrMessageEvent, a1: str = "", a2: str = "", a3: str = ""
    ):
        event.stop_event()

        args_str = f"{a1} {a2} {a3}".lower().strip()


        session_key = f"{event.unified_msg_origin}_{event.get_sender_id()}"
        if session_key in self.create_sessions:
            self.create_sessions[session_key]["last_active"] = time.time()
        if session_key in self.sessions:
            self.sessions[session_key]["last_active"] = time.time()
        if session_key in self.sessions and "quiz" in self.sessions[session_key]:
            yield event.plain_result(
                f"你已经在答题中了！请先完成或使用 {self.get_prefix()}quiz_stop 强制结束。"
            )
            return

        joined_args = args_str
        force_retry = "retry" in joined_args
        quiz_id = joined_args.replace("retry", "").replace(" ", "").strip()

        is_group = "group" in event.unified_msg_origin.lower()
        allow_group = True
        if is_group:
            val = self.config.get("allow_group_quiz", False)
            allow_group = str(val).lower() != "false"

        if not quiz_id:
            if is_group and not allow_group:
                yield event.plain_result(
                    f"🚫 防刷屏保护已开启：不支持在群聊内进行互动答题。\n👉 请前往与机器人的【私聊】窗口发送 {self.get_prefix()}quiz 发起测试！"
                )
                return
            self.sessions[session_key] = {
                "last_active": time.time(),
                "step": "AWAITING_QUIZ_ID",
            }
            yield event.plain_result(
                f"🎯 请发送您想测试的 【6位数问卷编码】（支持有无空格格式）\n（如果您不知道编码，可以先使用 {self.get_prefix()}quiz_list 查询所有可用测试）："
            )
            return

        quiz_data = self._load_quiz(quiz_id)
        if not quiz_data:
            if (
                session_key in self.sessions
                and self.sessions[session_key].get("step") == "AWAITING_QUIZ_ID"
            ):
                del self.sessions[session_key]
            yield event.plain_result(
                f"找不到编码为 {quiz_id} 的问卷。请检查代码是否输入有误。"
            )
            return

        if not force_retry:
            history = await self.db.get_user_history(event.get_sender_id(), quiz_id)
            if history:
                if "group" not in event.unified_msg_origin.lower():
                    yield event.plain_result(
                        f"🔥 系统检测到您之前已经测过这份问卷了！已为您智能调取当时的专属绝赞档案记录。\n（💡 偷偷告诉你：如果您想在群聊中炫耀结论，可以在任意已部署机器人的群内发送 {self.get_prefix()}quiz {quiz_id} 展示海报！\n如果您想刷新命运重拿剧本，请发送 {self.get_prefix()}quiz {quiz_id} retry）"
                    )
                try:
                    url = await self._render_poster(
                        event,
                        quiz_id,
                        quiz_data.get("title", "未知测试"),
                        history["result_name"],
                        history["ai_comment"],
                    )
                    yield event.image_result(url)
                except Exception as e:
                    yield event.plain_result(
                        f"（档案图片获取失败了：{e}）\n您的结果：{history['result_name']}\n评语：{history['ai_comment']}"
                    )
                return

        is_gacha = quiz_data.get("type") == "gacha"

        if is_group and not allow_group and not is_gacha:
            yield event.plain_result(
                f"🚫 防刷屏保护已开启：不支持在群聊内答题。\n👉 请前往与机器人的【私聊】窗口发送 {self.get_prefix()}quiz {quiz_id} 开始测试！\n✅ 答题后，可在群里使用该命令分享结果。"
            )
            return

        if is_gacha:
            outcomes = quiz_data.get("results_logic", {}).get("outcomes", [])
            if not outcomes:
                yield event.plain_result("该纯抽卡问卷奖池配置异常。")
                return
            
            picked = random.choice(outcomes)
            cat_name = picked.get("name", "神秘结果")
            base_desc = picked.get("desc", "没有更多描述。")
            
            yield event.plain_result("🎲 正在为您祈愿抽签，请稍候...")
            
            ai_comment = await generate_snarky_eval(
                self.context,
                self.config.get("provider_id", ""),
                quiz_data.get("title", "未知测试"),
                cat_name,
                base_desc,
                "群聊直出抽签，命运使然直接抽中了此签。",
                quiz_data.get("ai_tone", "神秘"),
                self._get_persona_prompt(event),
            )
            if not ai_comment:
                ai_comment = f"{cat_name}：{base_desc}"
                
            await self.db.record_play(
                event.get_sender_id(),
                event.get_sender_name(),
                quiz_id,
                cat_name,
                ai_comment,
            )
            
            try:
                url = await self._render_poster(
                    event,
                    quiz_id,
                    quiz_data.get("title", "未知测试"),
                    cat_name,
                    ai_comment,
                )
                yield event.image_result(url)
            except Exception as e:
                logger.error(f"Poster render failed: {e}")
                yield event.plain_result(
                    f"（结果海报生成失败）\n【{cat_name}】\n{ai_comment}"
                )
            return

        questions = quiz_data.get("questions", [])
        if not questions:
            yield event.plain_result("这个问卷没有题目。")
            return

        self.sessions[session_key] = {
            "last_active": time.time(),
            "test_id": quiz_id,
            "quiz": quiz_data,
            "current_q_idx": 0,
            "scores": {},
            "trajectory": [],
        }

        author = quiz_data.get("author", "未知作者")
        desc_line = f"\n📝 简介：{quiz_data['desc']}" if "desc" in quiz_data else ""

        yield event.plain_result(
            f"开始了！{quiz_data.get('title')} (作者: {author}){desc_line}\n\n{self._format_question(quiz_data, 0)}"
        )

    @filter.command("quiz_stop", alias=["退出测试", "停止测试", "结束答题", "取消", "退出"], priority=1)
    async def quiz_stop(self, event: AstrMessageEvent):
        event.stop_event()
        session_key = f"{event.unified_msg_origin}_{event.get_sender_id()}"
        if session_key in self.create_sessions:
            self.create_sessions[session_key]["last_active"] = time.time()
        if session_key in self.sessions:
            self.sessions[session_key]["last_active"] = time.time()
        if session_key in self.sessions:
            del self.sessions[session_key]
            yield event.plain_result("已强制结束当前答题。")

    @filter.command("quiz_help", alias=["测试帮助", "问卷帮助", "答题帮助"], priority=1)
    async def quiz_help(self, event: AstrMessageEvent):
        event.stop_event()
        p = self.get_prefix()
        help_text = f"""🍊 OrangeQuiz 使用指南

📋 答题指令
  {p}quiz / {p}测试 / {p}做题 / {p}答题
    → 开始一次测试（私聊推荐）
  {p}quiz <编号> / {p}测试 <编号>
    → 直接进入指定问卷（支持 123456 或 123 456 格式）
  {p}quiz <编号> retry
    → 重新作答同一份问卷
  {p}quiz_stop / {p}退出测试 / {p}停止测试
    → 中途强制退出当前答题

📚 查询指令
  {p}quiz_list / {p}测试列表 / {p}问卷列表
    → 查看所有可用问卷
  {p}quiz_hot / {p}热门测试 / {p}测试排名
    → 查看最受欢迎的 Top 5 问卷

✏️ 创建指令
  {p}quiz_create / {p}创建测试 / {p}新增问卷 / {p}出题
    → 用 AI 帮你创建一份全新问卷

❓ 帮助
  {p}quiz_help / {p}测试帮助
    → 显示本帮助页面

💡 提示：测试编号出现在海报上，格式为 6 位数字（如 123 456），可带空格也可不带空格直接发送。"""
        yield event.plain_result(help_text)

    def _format_question(self, quiz_data: dict, q_idx: int) -> str:
        q = quiz_data["questions"][q_idx]
        text = f"第 {q_idx + 1} 题: {q['text']}\n"
        for opt in q["options"]:
            text += f"{opt['label']}. {opt['text']}\n"
        text += "\n请回复选项（例如 A 或 B, 也可以回复 1 或 2）或回复“取消”退出答题"
        return text

    def _load_template(self, t_type: str, theme_name: str) -> str:
        theme_name = theme_name if theme_name else "default"
        plugin_dir = Path(__file__).parent
        tmpl_path = plugin_dir / "templates" / f"{t_type}_{theme_name}.html"
        if not tmpl_path.exists():
            tmpl_path = plugin_dir / "templates" / f"{t_type}_default.html"
        try:
            with open(tmpl_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.error(f"OrangeQuiz: Failed to load HTML template {tmpl_path}: {e}")
            return ""

    async def _render_poster(self, event, test_id, quiz_title, cat_name, snarky_eval):
        user_name = "玩家"
        if hasattr(event, "get_sender_name"):
            user_name = event.get_sender_name()

        display_id = str(test_id)
        if len(display_id) == 6:
            display_id = f"{display_id[:3]} {display_id[3:]}"

        footer_text = (
            "可以和bot私聊参与测试 \n -- 由 Astrbot 插件 OrangeQuiz 强力驱动 --"
        )
        invite_tip_text = "对自己发送以上带有编号的指令，立刻开始测试！"

        if self.config:
            if "footer_text" in self.config and self.config["footer_text"].strip():
                footer_text = self.config["footer_text"].replace("\\n", "\n")
            if (
                "invite_poster_tip" in self.config
                and self.config["invite_poster_tip"].strip()
            ):
                invite_tip_text = (
                    self.config["invite_poster_tip"]
                    .replace("{test_id}", display_id)
                    .replace("/quiz", f"{self.get_prefix()}quiz")
                )

        data = {
            "user_name": user_name,
            "quiz_title": quiz_title,
            "cat_name": cat_name,
            "ai_comment": snarky_eval,
            "display_id": display_id,
            "footer_text": footer_text,
            "invite_tip_text": invite_tip_text,
        }
        theme = self.config.get("result_theme", "default")
        html_str = self._load_template("result", theme)
        return await self.html_render(html_str, data)

    async def _render_invite_poster(
        self, event, test_id, quiz_title, q_count, author_name, quiz_desc
    ):
        display_id = str(test_id)
        if len(display_id) == 6:
            display_id = f"{display_id[:3]} {display_id[3:]}"

        footer_text = "使用 Astrbot 插件 OrangeQuiz 生成\n可以和bot私聊参与测试"
        invite_tip_text = "对bot发送以上带有编号的指令，开始同款测试，分享测试结果！"

        if self.config:
            if "footer_text" in self.config and self.config["footer_text"].strip():
                footer_text = self.config["footer_text"].replace("\\n", "\n")
            if (
                "invite_poster_tip" in self.config
                and self.config["invite_poster_tip"].strip()
            ):
                invite_tip_text = (
                    self.config["invite_poster_tip"]
                    .replace("{test_id}", display_id)
                    .replace("/quiz", f"{self.get_prefix()}quiz")
                )

        data = {
            "quiz_title": quiz_title,
            "q_count": q_count,
            "author_name": author_name,
            "quiz_desc": quiz_desc,
            "display_id": display_id,
            "footer_text": footer_text,
            "invite_tip_text": invite_tip_text,
        }
        theme = self.config.get("invite_theme", "default")
        html_str = self._load_template("invite", theme)
        return await self.html_render(html_str, data)

    def _format_preview(self, quiz_data: dict) -> str:
        q_count = len(quiz_data.get("questions", []))
        author = quiz_data.get("author", "未知作者")
        desc = quiz_data.get("desc", "暂无简介")
        summary = f"📋 【问卷预览】\n标题：{quiz_data.get('title')}\n简介：{desc}\n作者：{author}\n题数：{q_count}\n"

        if quiz_data.get("type") == "gacha":
            summary += (
                "分发机制：【纯抽卡盲盒（无需答题，群聊直出）】\n\n"
            )
            summary += "=== 可能摇出的结局池 ===\n"
            r_logic = quiz_data.get("results_logic", {})
            for r in r_logic.get("outcomes", []):
                summary += f"- {r.get('name')}\n"
        elif quiz_data.get("type") == "random":
            summary += (
                "分发机制：【盲盒抽签（答案不影响结局分配）】\n\n=== 详细题目 ===\n"
            )
            for idx, q in enumerate(quiz_data.get("questions", [])):
                summary += f"第 {idx + 1} 题: {q['text']}\n"
                opts_str = " ".join(
                    [f"{opt['label']}. {opt['text']}" for opt in q.get("options", [])]
                )
                summary += f"{opts_str}\n\n"

            summary += "=== 可能摇出的结局池 ===\n"
            r_logic = quiz_data.get("results_logic", {})
            for r in r_logic.get("outcomes", []):
                summary += f"- {r.get('name')}\n"
        else:
            summary += "分发机制：【数值积分累加】\n\n=== 详细题目 ===\n"
            for idx, q in enumerate(quiz_data.get("questions", [])):
                summary += f"第 {idx + 1} 题: {q['text']}\n"
                opts_list = []
                for opt in q.get("options", []):
                    w_str = ", ".join(
                        f"{k} +{v}" for k, v in opt.get("weights", {}).items()
                    )
                    opts_list.append(f"{opt['label']}. {opt['text']} (分值: {w_str})")
                summary += "\n".join(opts_list) + "\n\n"

            summary += "=== 结局鉴定 ===\n"
            r_logic = quiz_data.get("results_logic", {})
            if not r_logic:
                summary += "（暂无分类逻辑，请注意）\n"
            else:
                first_key = list(r_logic.keys())[0]
                if "ranges" in r_logic.get(first_key, {}):
                    range_list = r_logic[first_key]["ranges"]
                    summary += "计分类别区间：\n"
                    for r in range_list:
                        summary += (
                            f"- [{r.get('min')}-{r.get('max')} 分] : {r.get('name')}\n"
                        )
                else:
                    summary += "权重分类竞争：\n"
                    for cat, v in r_logic.items():
                        summary += f"- {v.get('name', cat)}\n"

        summary += "\n💡 您可以回复【提交】来正式启用它！或者直接发来修改意见（如'题目数量少一点'、'选项分值调整为……'），我会为您量身修改。"
        return summary

    # ─────────────────────────────────────────────────────────
    # on_message: 消息事件分发中枢（精简后只负责路由）
    # ─────────────────────────────────────────────────────────

    @filter.event_message_type(EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """消息总入口：过滤指令、更新时间戳、路由到对应处理器。"""
        msg = event.message_str.strip()

        # 跳过指令前缀（防止与 @filter.command 双重触发）
        if msg.startswith("/") or msg.startswith("!"):
            return

        cmd_keywords = [
            "quiz", "测试", "答题", "做题", "测试列表", "问卷列表",
            "热门测试", "测试排名", "创建测试", "新增问卷", "出题",
            "退出测试", "停止测试", "结束答题", "取消", "退出",
            "测试帮助", "问卷帮助", "答题帮助",
        ]
        if any(msg.startswith(kw) for kw in cmd_keywords):
            return

        await self._ensure_init()

        session_key = f"{event.unified_msg_origin}_{event.get_sender_id()}"

        # 更新活跃时间戳
        for sessions_map in [self.create_sessions, self.sessions]:
            if session_key in sessions_map:
                sessions_map[session_key]["last_active"] = time.time()

        # 全局退出拦截（同时清理出题和答题 session）
        if msg in ["退出", "取消", "不做了", "退", "结束"]:
            deleted = False
            for sessions_map in [self.create_sessions, self.sessions]:
                if session_key in sessions_map:
                    del sessions_map[session_key]
                    deleted = True
            if deleted:
                event.stop_event()
                yield event.plain_result("✅ 已为您强制取消当前的所有问卷操作。")
            return

        # 路由到出题 session 处理器
        if session_key in self.create_sessions:
            async for result in self._handle_create_session(event, session_key, msg):
                yield result
            return

        # 路由到答题 session 处理器
        if session_key in self.sessions:
            async for result in self._handle_quiz_session(event, session_key, msg):
                yield result

    # ─────────────────────────────────────────────────────────
    # 出题状态机处理器
    # ─────────────────────────────────────────────────────────

    async def _handle_create_session(self, event: AstrMessageEvent, session_key: str, msg: str):
        """处理出题流程各阶段。"""
        c_session = self.create_sessions[session_key]
        step = c_session.get("step")

        if step == "GENERATING":
            event.stop_event()
            return

        event.stop_event()

        if step == "AWAITING_TITLE":
            c_session["title"] = msg
            c_session["step"] = "AWAITING_CONTENT"
            yield event.plain_result(
                "好的！接下来，请描述你想要什么样的问卷（如：想要一个对男猫娘接受程度的问卷、想要两个问题的问卷，或者直接说\"如题\"），如果你有初步的问卷，也可以直接把你的问卷草稿粘贴在这里（AI 会帮您格式化为题目）："
            )
            return

        if step == "AWAITING_CONTENT":
            c_session["content"] = msg
            c_session["step"] = "AWAITING_TONE"
            yield event.plain_result(
                "收到！最后，您希望之后做这份问卷的人，在得到结果时收到 AI 什么语气的吐槽评语？（如：毒舌犀利、温柔可爱、发疯文学、阴阳怪气...也可以是：狐狸的口吻、猫娘的口吻...）"
            )
            return

        if step == "AWAITING_TONE":
            if "tone" not in c_session:
                c_session["tone"] = msg if msg else "毒舌犀利"
            async for result in self._generate_and_preview_quiz(event, session_key):
                yield result
            return

        if step == "AWAITING_CONFIRMATION":
            async for result in self._handle_confirmation(event, session_key, msg):
                yield result

    async def _generate_and_preview_quiz(self, event: AstrMessageEvent, session_key: str):
        """调用 LLM 生成问卷草稿并向用户展示预览。"""
        c_session = self.create_sessions[session_key]
        c_session["step"] = "GENERATING"
        yield event.plain_result("🔍 正在绞尽脑汁为你生成测试问卷，请稍候...")

        provider_id = await self.context.get_current_chat_provider_id(event.unified_msg_origin)

        actual_content = c_session["content"]
        if c_session.get("feedback_mod"):
            actual_content += (
                f"\n\n注意！我对之前生成的草稿不满意，请进行以下综合修改，重新出一份：\n{c_session['feedback_mod']}"
            )

        quiz_data = await generate_quiz(
            self.context,
            provider_id,
            c_session["title"],
            actual_content,
            c_session["tone"],
            persona_prompt=await self._get_persona_prompt(event),
        )

        if not quiz_data:
            c_session["step"] = "AWAITING_CONFIRMATION"
            yield event.plain_result(
                "生成或解析失败，AI脑子瓦特了。您可以输入【重生成】或其他修改要求重试，或发送【退出】。"
            )
            return

        author_name = event.get_sender_name() if hasattr(event, "get_sender_name") else "玩家"
        quiz_data["author"] = author_name
        c_session["draft_quiz"] = quiz_data
        c_session["step"] = "AWAITING_CONFIRMATION"

        warning = ""
        if len(quiz_data.get("questions", [])) > 6:
            warning = "\n⚠️ 提示：您生成的问卷题目过多（超越了推荐的 6 题限制）。如果您提交，可能会导致刷屏、体验不佳。"

        yield event.plain_result(self._format_preview(quiz_data) + warning)

    async def _handle_confirmation(self, event: AstrMessageEvent, session_key: str, msg: str):
        """处理用户在 AWAITING_CONFIRMATION 状态下的确认/修改/重生成操作。"""
        c_session = self.create_sessions[session_key]
        max_mod = int(self.config.get("max_modify_count", 8))

        if msg in ["提交", "确认", "确定", "好", "可以"]:
            quiz_data = c_session.get("draft_quiz")
            if not quiz_data:
                yield event.plain_result("草稿丢失，请发送修改意见重组或发送退出。")
                return

            def generate_6_digit() -> str:
                for _ in range(100):
                    code = str(random.randint(100000, 999999))
                    if not os.path.exists(self.quizzes_dir / f"{code}.json"):
                        return code
                raise RuntimeError("无法生成新的问卷 ID，已达到最大重试次数 100")

            test_id = generate_6_digit()
            quiz_data["test_id"] = test_id

            try:
                with open(self.quizzes_dir / f"{test_id}.json", "w", encoding="utf-8") as f:
                    json.dump(quiz_data, f, ensure_ascii=False, indent=2)
                await self.db.record_create(event.get_sender_id())
                yield event.plain_result(
                    f"✅ 保存并启用成功！分配的测试专享编码为： {test_id} \n\n别人可以直接发送：\n{self.get_prefix()}quiz {test_id}\n立刻开启本问卷的体验！"
                )
                try:
                    invite_url = await self._render_invite_poster(
                        event, test_id,
                        quiz_data.get("title", "未知测试"),
                        len(quiz_data.get("questions", [])),
                        quiz_data.get("author", "玩家"),
                        quiz_data.get("desc", "这是一份超有趣的属性鉴定测试，快来试试看吧！"),
                    )
                    if invite_url:
                        yield event.image_result(invite_url)
                except Exception:
                    pass
            except Exception as e:
                yield event.plain_result(f"保存问卷失败：{e}")

            if session_key in self.create_sessions:
                del self.create_sessions[session_key]
            return

        # ── 修改类操作 ───────────────────────────────────────
        if c_session.get("mod_count", 0) >= max_mod:
            yield event.plain_result(
                f"⚠️ 本次生成的重试/修改次数已经耗尽（上限 {max_mod} 次）。请您在上述生成的版本中回复【提交】，或者发送【退出】以释放配额。"
            )
            return

        c_session["mod_count"] = c_session.get("mod_count", 0) + 1

        if msg == "重生成":
            c_session["feedback_mod"] = ""
            yield event.plain_result(
                f"好的，正在为您原样重新生成一版...(耗用修改次数: {c_session['mod_count']}/{max_mod})"
            )
        else:
            prior_fb = c_session.get("feedback_mod", "")
            new_fb = f"第 {c_session['mod_count']} 次修改要求：{msg}"
            c_session["feedback_mod"] = f"{prior_fb}\n{new_fb}" if prior_fb else new_fb
            yield event.plain_result(
                f"收到您的修改要求，正在打翻重做，请稍候...(耗用修改次数: {c_session['mod_count']}/{max_mod})"
            )

        async for result in self._generate_and_preview_quiz(event, session_key):
            yield result

    # ─────────────────────────────────────────────────────────
    # 答题状态机处理器
    # ─────────────────────────────────────────────────────────

    async def _handle_quiz_session(self, event: AstrMessageEvent, session_key: str, msg: str):
        """处理用户答题过程的全生命周期。"""
        session = self.sessions[session_key]

        if session.get("step") == "AWAITING_QUIZ_ID":
            event.stop_event()
            quiz_id = event.message_str.strip().replace(" ", "")
            quiz_data = self._load_quiz(quiz_id)
            if not quiz_data:
                del self.sessions[session_key]
                yield event.plain_result(f"找不到编码为 {quiz_id} 的问卷，已为您取消当前操作。")
                return
            questions = quiz_data.get("questions", [])
            if not questions:
                del self.sessions[session_key]
                yield event.plain_result("这个问卷没有题目，已为您取消。")
                return
            self.sessions[session_key] = {
                "last_active": time.time(),
                "test_id": quiz_id,
                "quiz": quiz_data,
                "current_q_idx": 0,
                "scores": {},
                "trajectory": [],
            }
            yield event.plain_result(
                f"开始了！{quiz_data.get('title')}\n\n{self._format_question(quiz_data, 0)}"
            )
            return

        if session.get("generating"):
            return

        quiz_data = session["quiz"]
        q_idx = session["current_q_idx"]
        question = quiz_data["questions"][q_idx]

        # 规范化用户输入：全角→半角，提取首个字母/数字，数字映射到选项标签
        fullwidth_map = str.maketrans(
            "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ",
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",
        )
        normalized = msg.translate(fullwidth_map)
        match = re.search(r"([A-Za-z0-9]+)", normalized)
        answer = match.group(1).upper() if match else normalized.upper()
        if answer.isdigit():
            idx = int(answer) - 1
            if 0 <= idx < len(question["options"]):
                answer = str(question["options"][idx].get("label", "")).strip().upper()

        valid_labels = [str(opt.get("label", "")).strip().upper() for opt in question["options"]]
        if answer not in valid_labels:
            event.stop_event()
            yield event.plain_result(f"无效的选项，请重新输入（有效选项: {', '.join(valid_labels)}）")
            return

        selected_opt = next(
            (opt for opt in question["options"] if str(opt.get("label", "")).strip().upper() == answer),
            None,
        )
        if selected_opt and "weights" in selected_opt:
            for category, weight in selected_opt["weights"].items():
                session["scores"][category] = session["scores"].get(category, 0) + weight

        opt_text = selected_opt["text"] if selected_opt else answer
        session["trajectory"].append(f"Q: {question['text']} -> A: {opt_text}")
        session["current_q_idx"] += 1
        q_idx = session["current_q_idx"]

        if q_idx < len(quiz_data["questions"]):
            event.stop_event()
            yield event.plain_result(self._format_question(quiz_data, q_idx))
            return

        # ── 答题结束，进入结算 ──────────────────────────────────
        event.stop_event()
        session["generating"] = True
        yield event.plain_result("🔍 正在为您生成结算报告，请稍候...")

        cat_name, cat_desc = self._resolve_result(quiz_data, session)

        provider_id = await self.context.get_current_chat_provider_id(event.unified_msg_origin)
        traj_str = "\n".join(session["trajectory"])
        tone = quiz_data.get("ai_tone", "可爱+专业")

        snarky_eval = ""
        for attempt in range(3):
            try:
                snarky_eval = await asyncio.wait_for(
                    generate_snarky_eval(
                        self.context, provider_id,
                        quiz_data.get("title", "未知测试"),
                        cat_name, cat_desc, traj_str, tone,
                        persona_prompt=await self._get_persona_prompt(event),
                    ),
                    timeout=60.0,
                )
                break
            except Exception as e:
                logger.error(f"Failed to generate snarky eval: {e}", exc_info=True)
                if attempt == 2:
                    if session_key in self.sessions:
                        del self.sessions[session_key]
                    yield event.plain_result("⚠️ 生成 AI 评论连续 3 次超时或失败，已自动取消本次结算。请稍后再试。")
                    return
                await asyncio.sleep(2)

        result_text = f"🏆 测试完成！\n结果：{cat_name}\nAI 解读：\n{snarky_eval}"

        try:
            user_id = event.get_sender_id()
            user_name = event.get_sender_name() if hasattr(event, "get_sender_name") else "玩家"
            await self.db.record_play(user_id, user_name, session["test_id"], cat_name, snarky_eval)

            url = None
            for attempt in range(3):
                try:
                    url = await asyncio.wait_for(
                        self._render_poster(
                            event, session["test_id"],
                            quiz_data.get("title", "未知测试"),
                            cat_name, snarky_eval,
                        ),
                        timeout=60.0,
                    )
                    break
                except Exception as e:
                    if attempt == 2:
                        raise e
                    await asyncio.sleep(2)

            if session_key in self.sessions:
                del self.sessions[session_key]

            yield event.image_result(url)

            if "group" not in event.unified_msg_origin.lower():
                yield event.plain_result(
                    f"💡 偷偷告诉你：如果您想在群聊中炫耀结论，可以在群内发送 {self.get_prefix()}quiz {session['test_id']} 展示海报！\n如果您想刷新命运重测一次，请发送 {self.get_prefix()}quiz {session['test_id']} retry"
                )
        except Exception as e:
            if session_key in self.sessions:
                del self.sessions[session_key]
            yield event.plain_result(result_text + f"\n\n(图片生成已降级，因出现错误：{e})")

    def _resolve_result(self, quiz_data: dict, session: dict) -> tuple:
        """根据问卷类型和答题分数，计算最终结果分类名称与描述。"""
        if quiz_data.get("type") == "random":
            outcomes = quiz_data.get("results_logic", {}).get("outcomes", [])
            if outcomes:
                picked = random.choice(outcomes)
                return picked.get("name", "神秘随机结果"), picked.get("desc", "")
            return "未定义随机", ""

        scores = session.get("scores", {})
        if not scores:
            return "未知", "在没有得分中结束"

        max_cat = max(scores, key=scores.get)
        cat_score = scores[max_cat]
        result_logic = quiz_data.get("results_logic", {}).get(max_cat, {})

        if "ranges" in result_logic:
            for r in result_logic["ranges"]:
                if r["min"] <= cat_score <= r["max"]:
                    return r.get("name", max_cat), r.get("desc", r.get("base_desc", ""))
        return result_logic.get("name", max_cat), result_logic.get("base_desc", "")

