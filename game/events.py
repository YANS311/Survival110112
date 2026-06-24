# game/events.py
"""
动态事件系统：每月结算时根据玩家状态触发随机事件
"""
import random
from dataclasses import dataclass, field
from typing import Optional, Callable
from datetime import date


@dataclass
class EventEffect:
    """事件效果数据结构"""
    money: int = 0
    hp: int = 0
    san: int = 0
    thesis: float = 0.0
    thesis停滞: bool = False  # 论文停滞标记
    flag_set: dict = field(default_factory=dict)  # 设置的标记
    flag_clear: list = field(default_factory=list)  # 清除的标记
    game_over: bool = False
    ending_type: Optional[str] = None


@dataclass
class GameEvent:
    """游戏事件数据结构"""
    id: str
    name: str
    description: str
    effect: EventEffect
    # 触发条件函数：返回 True 表示可以触发
    condition: Callable = field(default_factory=lambda: lambda player, month: True)
    # 事件权重（越高越容易触发）
    weight: int = 100
    # 是否为强制事件（不参与随机抽取，满足条件直接触发）
    is_mandatory: bool = False
    # 是否为负面事件（用于某些机制判断）
    is_negative: bool = True


# ═══════════════════════════════════════════════════════════════════════════════
# 事件池定义
# ═══════════════════════════════════════════════════════════════════════════════

EVENT_POOL: list[GameEvent] = [
    # ── 1. 组会背刺 ──────────────────────────────────────────────────────────
    GameEvent(
        id='GROUP_MEETING_BACKSTAB',
        name='【组会背刺】',
        description='导师突然在群里@所有人："明天组会，每人都要汇报进度。" 你看着刚写了个 title 的论文，连夜赶制 PPT。',
        effect=EventEffect(san=-30, hp=-5),
        condition=lambda player, month: player.current_district in ('110105', '110108'),
        weight=120,
        is_negative=True,
    ),

    # ── 2. 大桃熟了 ──────────────────────────────────────────────────────────
    GameEvent(
        id='PINGGU_PEACH',
        name='【大桃熟了】',
        description='路过 852 车站，路边的平谷大桃又大又甜，你忍不住买了一个。咬一口，汁水四溢，论文的烦恼暂时被甜味冲淡。但你在这颗桃上花了整整一个小时。',
        effect=EventEffect(money=-15, san=20, thesis停滞=True),
        condition=lambda player, month: (
            player.current_district == '110117' and 5 <= month.month <= 8
        ),
        weight=80,
        is_negative=False,
    ),

    # ── 3. 燕郊跨省断网 ──────────────────────────────────────────────────────
    GameEvent(
        id='YANJIAO_NETWORK_OUTAGE',
        name='【燕郊跨省断网】',
        description='手机在白庙检查站失去信号，正在跑的 AutoDL 调参任务因为断网超时被 kill -9。你看着屏幕上 "Process terminated" 的红字，感觉自己的学术生涯也被 terminate 了。',
        effect=EventEffect(san=-15),
        condition=lambda player, month: player.current_district == '131082',
        weight=100,
        is_negative=True,
    ),

    # ── 4. 服务器被占 ────────────────────────────────────────────────────────
    GameEvent(
        id='GPU_SERVER_HOGGED',
        name='【服务器被占】',
        description='同实验室的昌平学长把 4080 显卡占满了，你的 DeepFM 推荐系统任务被无情 kill -9。你看着 nvidia-smi 里 100% 的利用率，和自己 0% 的论文进度，陷入了沉默。',
        effect=EventEffect(san=-20, thesis停滞=True),
        condition=lambda player, month: True,  # 任何地方都可能触发
        weight=90,
        is_negative=True,
    ),

    # ── 5. 地铁偶遇导师 ──────────────────────────────────────────────────────
    GameEvent(
        id='METRO_ADVISOR_ENCOUNTER',
        name='【地铁偶遇导师】',
        description='你在 6 号线上偶遇了导师。导师亲切地问你"最近论文写得怎么样了？" 你支支吾吾，导师的脸色越来越难看。',
        effect=EventEffect(san=-25, hp=-3),
        condition=lambda player, month: player.san < 60,
        weight=70,
        is_negative=True,
    ),

    # ── 6. 奖学金到账 ────────────────────────────────────────────────────────
    GameEvent(
        id='SCHOLARSHIP_ARRIVED',
        name='【奖学金到账】',
        description='银行卡突然收到一笔转账：国家助学金 6000 元！你看着余额，感觉这个月的房租有着落了。',
        effect=EventEffect(money=6000, san=15),
        condition=lambda player, month: month.month == 10 and month.year == 2026,
        weight=200,  # 高权重确保触发
        is_mandatory=True,
        is_negative=False,
    ),

    # ── 7. 论文被拒 ──────────────────────────────────────────────────────────
    GameEvent(
        id='PAPER_REJECTED',
        name='【论文被拒】',
        description='你收到了顶会的 rejection letter："The paper is below the acceptance threshold." 你看着那封冰冷的邮件，感觉自己的心血白费了。',
        effect=EventEffect(san=-35, thesis=-5),
        condition=lambda player, month: player.thesis_progress > 50,
        weight=60,
        is_negative=True,
    ),

    # ── 8. 实验跑通了 ────────────────────────────────────────────────────────
    GameEvent(
        id='EXPERIMENT_SUCCESS',
        name='【实验跑通了】',
        description='你的消融实验终于跑出了显著提升！看着 loss 曲线稳步下降，你第一次觉得自己的论文有希望了。',
        effect=EventEffect(san=25, thesis=8),
        condition=lambda player, month: player.thesis_progress > 30 and player.san < 50,
        weight=50,
        is_negative=False,
    ),

    # ── 9. 室友搬走 ──────────────────────────────────────────────────────────
    GameEvent(
        id='ROOMMATE_LEFT',
        name='【室友搬走】',
        description='你的室友找到了工作，搬去了西二旗。宿舍突然变得空荡荡的，只剩下你和一堆没洗的衣服。',
        effect=EventEffect(san=-10),
        condition=lambda player, month: player.current_district is None and player.school_code == '110105',
        weight=40,
        is_negative=True,
    ),

    # ── 10. 隔壁组会崩了 ─────────────────────────────────────────────────────
    GameEvent(
        id='OTHER_GROUP_COLLAPSED',
        name='【隔壁组会崩了】',
        description='听说隔壁组有个师兄被导师骂哭了，你突然觉得自己的处境也没那么糟。',
        effect=EventEffect(san=10),
        condition=lambda player, month: player.san < 40,
        weight=60,
        is_negative=False,
    ),

    # ── 11. 外卖吃坏肚子 ─────────────────────────────────────────────────────
    GameEvent(
        id='BAD_TAKEOUT',
        name='【外卖吃坏肚子】',
        description='你贪便宜点了拼好饭，结果拉了一晚上肚子。明天组会又得请假了。',
        effect=EventEffect(hp=-15, san=-10),
        condition=lambda player, month: player.money < 2000,
        weight=70,
        is_negative=True,
    ),

    # ── 12. 通勤地铁故障 ─────────────────────────────────────────────────────
    GameEvent(
        id='SUBWAY_BREAKDOWN',
        name='【通勤地铁故障】',
        description='6 号线又双叒叕故障了！你在定福庄站等了 40 分钟，论文又少写了一章。',
        effect=EventEffect(san=-20, hp=-8),
        condition=lambda player, month: player.current_district in ('110105', '110112', '131082'),
        weight=80,
        is_negative=True,
    ),

    # ── 13. 师兄请客 ─────────────────────────────────────────────────────────
    GameEvent(
        id='SENIOR_TREATS',
        name='【师兄请客】',
        description='师兄拿到了大厂 offer，请大家吃海底捞。你吃了三盘肥牛，暂时忘记了论文的痛苦。',
        effect=EventEffect(money=-200, san=30, hp=5),
        condition=lambda player, month: True,
        weight=50,
        is_negative=False,
    ),

    # ── 14. 路边捡到优惠券 ───────────────────────────────────────────────────
    GameEvent(
        id='FOUND_COUPON',
        name='【路边捡到优惠券】',
        description='你在定福庄南门捡到一张瑞幸 9.9 元优惠券，今天的咖啡有着落了。',
        effect=EventEffect(money=-10, san=5),
        condition=lambda player, month: True,
        weight=30,
        is_negative=False,
    ),

    # ── 15. 深夜emo ──────────────────────────────────────────────────────────
    GameEvent(
        id='MIDNIGHT_EMO',
        name='【深夜emo】',
        description='凌晨三点，你看着天花板，开始思考人生的意义。论文、工作、房租……所有压力一起涌上来。',
        effect=EventEffect(san=-20, thesis停滞=True),
        condition=lambda player, month: player.san < 50 and player.hp < 60,
        weight=60,
        is_negative=True,
    ),

    # ── 16. 天通苑合租奇遇 ───────────────────────────────────────────────────
    GameEvent(
        id='TIANTONGYU_ADVENTURE',
        name='【天通苑合租奇遇】',
        description='你的室友是个程序员，每天凌晨两点还在敲键盘。他的机械键盘声让你整晚睡不着，但你们也成了可以一起吐槽北京的朋友。',
        effect=EventEffect(san=10, hp=-5),
        condition=lambda player, month: player.current_district == '110114',
        weight=60,
        is_negative=False,
    ),

    # ── 17. 燕郊大雾 ─────────────────────────────────────────────────────────
    GameEvent(
        id='YANJIAO_FOG',
        name='【燕郊大雾】',
        description='今天燕郊大雾，能见度不足 10 米。你站在检查站前，感觉自己像是活在《寂静岭》里。',
        effect=EventEffect(san=-15, hp=-10),
        condition=lambda player, month: player.current_district == '131082',
        weight=50,
        is_negative=True,
    ),

    # ── 18. 中关村蹭课 ───────────────────────────────────────────────────────
    GameEvent(
        id='ZGC_FREeload_LECTURE',
        name='【中关村蹭课】',
        description='你在五道口蹭了一节清华的深度学习课，感觉自己的论文思路又打开了。',
        effect=EventEffect(san=10, thesis=3),
        condition=lambda player, month: player.current_district == '110108',
        weight=40,
        is_negative=False,
    ),

    # ── 19. 实验室空调坏了 ───────────────────────────────────────────────────
    GameEvent(
        id='LAB_AC_BROKEN',
        name='【实验室空调坏了】',
        description='七月份，实验室空调坏了。你在 35 度的高温下改论文，感觉自己的智商在蒸发。',
        effect=EventEffect(hp=-20, san=-15),
        condition=lambda player, month: month.month in (7, 8),
        weight=70,
        is_negative=True,
    ),

    # ── 20. 导师表扬 ─────────────────────────────────────────────────────────
    GameEvent(
        id='ADVISOR_PRAISE',
        name='【导师表扬】',
        description='你在组会上展示了最新的实验结果，导师难得地说了一句"做得不错"。你感觉这一年都值了。',
        effect=EventEffect(san=20, thesis=5),
        condition=lambda player, month: player.thesis_progress > 40 and player.san > 30,
        weight=40,
        is_negative=False,
    ),
]


# ═══════════════════════════════════════════════════════════════════════════════
# 事件管理器
# ═══════════════════════════════════════════════════════════════════════════════

class DynamicEventManager:
    """动态事件管理器"""

    def __init__(self, event_pool: list[GameEvent] = None):
        self.event_pool = event_pool or EVENT_POOL
        self.history: list[str] = []  # 已触发事件 ID 记录（防重复）

    def get_available_events(self, player, month) -> list[GameEvent]:
        """获取当前可触发的事件列表"""
        available = []
        for event in self.event_pool:
            # 跳过已触发的强制事件
            if event.is_mandatory and event.id in self.history:
                continue
            # 检查触发条件
            if event.condition(player, month):
                available.append(event)
        return available

    def select_event(self, player, month) -> Optional[GameEvent]:
        """根据权重随机选择一个事件"""
        available = self.get_available_events(player, month)

        if not available:
            return None

        # 分离强制事件和随机事件
        mandatory = [e for e in available if e.is_mandatory]
        if mandatory:
            return mandatory[0]  # 强制事件优先

        # 按权重随机选择
        total_weight = sum(e.weight for e in available)
        if total_weight == 0:
            return None

        rand_val = random.uniform(0, total_weight)
        cumulative = 0
        for event in available:
            cumulative += event.weight
            if rand_val <= cumulative:
                return event

        return available[-1]  # 兜底

    def trigger_event(self, player, month) -> Optional[dict]:
        """触发事件并返回结果"""
        event = self.select_event(player, month)

        if not event:
            return None

        # 记录已触发
        self.history.append(event.id)

        # 应用效果
        effect = event.effect

        # 论文停滞特殊处理
        if effect.thesis停滞:
            # 本月论文不增长（通过设置标记实现）
            player._thesis_stalled = True

        # 数值变化
        player.money = round(player.money + effect.money, 2)
        player.hp = round(player.hp + effect.hp, 2)
        player.san = round(player.san + effect.san, 2)
        player.thesis_progress = round(player.thesis_progress + effect.thesis, 2)

        # 确保数值不越界
        player.hp = max(0, min(100, player.hp))
        player.san = max(0, min(float(player.san_cap), player.san))
        player.money = max(-10000, player.money)  # 允许一定负债

        # 设置标记
        for key, value in effect.flag_set.items():
            setattr(player, key, value)
        for key in effect.flag_clear:
            if hasattr(player, key):
                setattr(player, key, False)

        # 结局判定
        if effect.game_over:
            player.is_game_over = True
            player.ending_type = effect.ending_type

        player.save()

        return {
            'event': event,
            'effect': effect,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 文本渲染器：generate_survival_log
# ═══════════════════════════════════════════════════════════════════════════════

def generate_survival_log(state: dict) -> str:
    """
    根据玩家状态生成生存日志文本。

    参数:
        state: 包含以下字段的字典
            - money: float, 当前余额
            - hp: float, 体力值
            - san: float, 理智值
            - current_district: str, 当前所在区域代码
            - ending_type: str, 结局类型（可选）

    返回:
        str: 生成的日志文本
    """
    money = state.get('money', 0)
    hp = state.get('hp', 100)
    san = state.get('san', 100)
    district = state.get('current_district', '')
    ending_type = state.get('ending_type', '')

    # ── 特殊结局文本 ──────────────────────────────────────────────────────────
    if ending_type == 'GRADUATED' and money < 3000:
        return (
            "拿到了沉甸甸的纸，但我交完下个月燕郊的房租后，卡里只剩下一碗兰州拉面的钱。"
            "昌平学长说得对，15号线带不走没有 Offer 的灵魂。\n\n"
            "毕业典礼上，导师拍着我的肩膀说'以后常联系'，我知道这是一句永远不会兑现的客套话。"
            "回到出租屋，我开始更新简历——用那台跑了三年论文的破电脑。"
        )

    # ── 顺义专属文本 ──────────────────────────────────────────────────────────
    if district == '110113':
        shunyi_snippets = [
            "俸伯站的风很大，吹得我睁不开眼。15号线的末班车还有最后一趟，我必须赶上。",
            "顺义牛栏山的二锅头比论文好入口，但喝完之后头更疼了。",
            "飞机从头顶轰鸣而过，我抬头望去，那是别人的人生，正在起飞。",
            "15号线的车厢里空荡荡的，和我的论文进度一样荒凉。",
            "俸伯站出口的共享单车又涨价了，从1.5涨到2块。我的钱包和论文一样，都在缩水。",
        ]
        base_text = random.choice(shunyi_snippets)
    elif district == '110117':
        base_text = "平谷的桃香飘了过来，但我的论文连个果子都没结。"
    elif district == '131082':
        base_text = "燕郊的房价又涨了，但我的工资（补助金）还是那一千块。"
    elif district == '110114':
        base_text = "天通苑的地铁站永远那么多人，就像我的参考文献一样拥挤。"
    elif district == '110112':
        base_text = "通州的大运河还在流淌，我的论文却卡在了第三章。"
    elif district == '110105':
        base_text = "定福庄的烟火气还在，但我的学术热情已经熄灭了。"
    elif district == '110108':
        base_text = "中关村的咖啡馆里坐满了讨论论文的人，而我只想逃离。"
    else:
        base_text = "北京的风很大，吹走了我的头发，也吹走了我的灵感。"

    # ── SAN 值低时的呓语文本 ──────────────────────────────────────────────────
    if san < 20:
        insane_snippets = [
            "我的脑质子正在被 Neo4j 构建成无法解析的环……",
            "RAG 的召回率变成了 0，我找不到我的导师了……",
            "Attention 机制在我的脑子里 self-attention，每一条神经都在尖叫……",
            "梯度爆炸了，我的理智也是。",
            "Embedding 层已经 overflow，我的人格向量正在发散……",
            "Loss 没有收敛，我的人生也没有……",
            "GPU 显存满了，我的脑容量也满了，但都是乱码……",
            "Dropout rate 设成了 0.9，我的记忆只剩下 10%……",
        ]
        insane_text = random.choice(insane_snippets)
        return f"{base_text}\n\n⚠️ 警告：理智值过低，系统日志出现乱码——\n{insane_text}"

    # ── HP 低时的虚弱文本 ─────────────────────────────────────────────────────
    if hp < 30:
        weak_snippets = [
            "你感觉自己的身体像是被 CUDA OOM 反复折磨的显卡，随时可能蓝屏。",
            "每走一步都像是在跑一个 O(n³) 的算法，效率极低，痛苦极高。",
            "你的体力条已经见底，就像你的论文进度条一样令人绝望。",
        ]
        return f"{base_text}\n\n{random.choice(weak_snippets)}"

    # ── 正常状态文本 ──────────────────────────────────────────────────────────
    if money < 0:
        return f"{base_text}\n\n💸 余额为负，你已经开始吃土了。但论文还是要写的。"
    elif money > 10000:
        return f"{base_text}\n\n💰 手头还算宽裕，至少这个月的房租不用愁了。但你知道，钱总有花完的一天。"
    else:
        return base_text


# ═══════════════════════════════════════════════════════════════════════════════
# 生存挣扎机制：黑市交易、三河大神、挖矿回血
# ═══════════════════════════════════════════════════════════════════════════════

def check_survival_struggle(player) -> Optional[dict]:
    """
    检查是否触发生存挣扎机制。
    返回可选操作列表，或 None 表示无特殊事件。
    """
    options = []

    # ── 1. 水导黑市交易 ──────────────────────────────────────────────────────
    if player.money < 0 and player.current_district in ('110108', '110105'):
        options.append({
            'type': 'black_market_deal',
            'name': '【水导黑市交易】',
            'desc': f'你的账户余额为 {player.money:.0f} 元。水导说："来我这打个横向，立刻给你 3000 块。"',
            'action': 'water_guide_horizontal',
            'money_gain': 3000,
            'thesis_penalty': -20,  # 强制降低 20%
            'hp_max_penalty': -5,  # 永久降低 HP 上限
        })

    # ── 2. 理智崩塌的网吧难民 ────────────────────────────────────────────────
    # 注意：SAN=0 时不触发，只有 SAN<0 时才触发（与 logic.py 保持一致）
    if player.san < 0 and player.current_district == '131082' and not player.is_game_over:
        options.append({
            'type': 'sanhe_master',
            'name': '【三河大神觉醒】',
            'desc': '你的理智归零了。在燕郊的一间网吧里，你找到了人生的终极答案——日结打零工，活在当下。',
            'action': 'become_sanhe_master',
            'ending_type': 'SANHE_MASTER',
        })

    # ── 3. 4080 挖矿回血 ─────────────────────────────────────────────────────
    if player.money < 1000 and player.hp > 30:
        # 检查是否已经开启挖矿
        mining_flag = getattr(player, 'gpu_mining_active', False)
        detection_rate = getattr(player, 'mining_detection_rate', 0)

        if not mining_flag:
            options.append({
                'type': 'gpu_mining',
                'name': '【4080 挖矿回血】',
                'desc': '你看着实验室那台闲置的 4080，心里冒出一个危险的想法……',
                'action': 'start_mining',
                'monthly_income': 800,
                'initial_detection_rate': 0.15,
            })
        else:
            # 已经在挖矿，检查是否被抓
            if random.random() < detection_rate:
                options.append({
                    'type': 'mining_busted',
                    'name': '【挖矿被抓】',
                    'desc': '导师发现了你在用 4080 挖矿。"学术不端"的帽子扣了下来……',
                    'action': 'mining_busted',
                    'ending_type': 'ACADEMIC_FRAUD',
                })

    return options if options else None


def execute_survival_struggle(player, option: dict) -> dict:
    """执行生存挣扎选项"""
    action = option.get('action')

    if action == 'water_guide_horizontal':
        player.money += 3000
        player.thesis_progress = max(0, player.thesis_progress - 20)
        player.hp_max = getattr(player, 'hp_max', 100) - 5
        player.has_research_fund = True
        player.save()
        return {'success': True, 'msg': '你成了水导的横向牛马，拿到了 3000 块，但论文进度暴跌。'}

    elif action == 'become_sanhe_master':
        player.ending_type = 'SANHE_MASTER'
        player.is_game_over = True
        player.current_district = None
        player.monthly_allowance = 0
        player.save()
        return {'success': True, 'msg': '你正式成为三河大神，在燕郊的网吧里找到了人生的意义。'}

    elif action == 'start_mining':
        player.gpu_mining_active = True
        player.mining_detection_rate = 0.15
        player.save()
        return {'success': True, 'msg': '你开始偷偷用 4080 挖矿，每月 +800 元。但小心，被抓的几率每月递增 15%。'}

    elif action == 'mining_busted':
        player.ending_type = 'ACADEMIC_FRAUD'
        player.is_game_over = True
        player.save()
        return {'success': True, 'msg': '你因学术不端被遣送回籍，学术生涯就此终结。'}

    return {'success': False, 'msg': '未知操作'}
