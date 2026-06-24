import datetime

from django.db import models
from django.contrib.auth.models import User

from game.constants import DISTRICT_DATA


class Player(models.Model):
    SCHOOL_CHOICES = [
        ('110105', '朝阳区某传媒高校 (CUC)'),
        ('110108', '海淀区某顶级学府 (PKU)'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    school_code = models.CharField(max_length=6, choices=SCHOOL_CHOICES)
    
    # 通关次数统计
    cuc_completion_count = models.IntegerField(default=0)  # CUC通关次数
    pku_completion_count = models.IntegerField(default=0)  # PKU通关次数

    # 四大核心数值 (统一为 Float 避免精度报错)
    money = models.FloatField(default=5000.0)  # 💰
    hp = models.FloatField(default=100.0)  # ❤️
    san = models.FloatField(default=100.0)  # 🧠 (允许跌破 0)
    san_cap = models.IntegerField(default=100)  # 🆕 精神上限 (每月清算时重置为100)
    # 🆕 记录下个月的上限，默认为 100。如果本月买了订阅，这里变成 120
    next_month_san_cap = models.IntegerField(default=100)
    is_in_renewal_crisis = models.BooleanField(default=False)
    thesis_progress = models.FloatField(default=0.0)  # 🎓

    # 状态标记
    current_month = models.DateField(auto_now_add=False)
    is_dorm_cleared = models.BooleanField(default=False)
    is_graduated = models.BooleanField(default=False)

    # 租房相关
    current_district = models.CharField(max_length=20, null=True, blank=True)
    # 🆕 租约到期日期
    rent_contract_end = models.DateField(null=True, blank=True)
    # 🆕 是否拥有押金在房东手里（搬家时才能退，或者毁约扣除）
    deposit_held = models.FloatField(default=0.0)

    monthly_allowance = models.FloatField(default=1000.0)

    # 结局相关
    is_game_over = models.BooleanField(default=False)
    ending_type = models.CharField(max_length=50, null=True, blank=True)

    # 精神废料 (纪念品背包，存逗号分隔的字符串)
    souvenirs_owned = models.TextField(default="", blank=True)
    has_moved_this_month = models.BooleanField(default=False)  # 🆕 每月搬家标记
    
    # 导师的科研经费 Buff
    has_research_fund = models.BooleanField(default=False)  # 是否拥有科研经费

    # 行为序列
    action_history = models.TextField(default="", blank=True)  # 存储逗号分隔的动作字符串

    # 🆕 生存挣扎机制字段
    hp_max = models.FloatField(default=100.0)  # HP 上限（水导黑市交易可永久降低）
    gpu_mining_active = models.BooleanField(default=False)  # 是否在挖矿
    mining_detection_rate = models.FloatField(default=0.0)  # 挖矿被抓概率
    dorm_eviction_phase_1_done = models.BooleanField(default=False)
    dorm_eviction_phase_2_done = models.BooleanField(default=False)
    dorm_eviction_phase_3_done = models.BooleanField(default=False)
    dorm_eviction_forced_done = models.BooleanField(default=False)
    temp_housing_active = models.BooleanField(default=False)  # 临时包住状态（航司/企业提供）
    dorm_eviction_rented = models.BooleanField(default=False)  # 宿舍清退时已租房
    dorm_eviction_prep_start = models.BooleanField(default=False)  # 宿舍清退准备阶段标记
    dorm_eviction_tried_beg = models.BooleanField(default=False)  # 尝试求情标记
    dorm_eviction_ignored = models.BooleanField(default=False)  # 忽略通知标记
    dorm_eviction_shared = models.BooleanField(default=False)  # 找师兄合租标记
    dorm_eviction_denial = models.BooleanField(default=False)  # 摆烂标记
    dorm_eviction_delayed = models.BooleanField(default=False)  # 延期标记

    @property
    def souvenirs_list(self):
        """前端模板调用，返回列表"""
        return [s for s in self.souvenirs_owned.split(',') if s]

    def is_homeless(self):
        if self.school_code == '110105' and not self.is_dorm_cleared:
            return False
        return not self.current_district

    def get_district_name(self):
        if not self.current_district:
            return "街头"
        dist = DISTRICT_DATA.get(self.current_district)
        return dist['name'] if dist else "未知区域"

    def __str__(self):
        return f"{self.user.username} - {self.school_code}"

    @property
    def region_name(self):
        """区域简称（学校所在区域）"""
        return "定福庄" if self.school_code == '110105' else "中关村"

    @property
    def death_location_name(self):
        """死亡时的实际位置简称"""
        if not self.current_district:
            return self.region_name  # 流浪时显示学校区域
        location_names = {
            '110108': '中关村',
            '110105': '定福庄',
            '110112': '通州',
            '110114': '天通苑',
            '110113': '顺义',
            '131082': '燕郊',
            '110115': '亦庄',
            '110117': '平谷',
        }
        return location_names.get(self.current_district, self.region_name)

    @property
    def spot_code(self):
        """精神图腾代码"""
        return "110114" if self.school_code == '110105' else "110108"

    @property
    def study_building(self):
        """专属自习室"""
        return "国重大楼" if self.school_code == '110105' else "理科一号楼"

    @property
    def gate_name(self):
        """挂逼网吧所在地"""
        return "传媒大学南门外" if self.school_code == '110105' else "北大东门外"

    @property
    def survival_months(self):
        """计算活了多少个月"""
        start_date = datetime.date(2025, 9, 1)
        # 计算年份差 * 12 + 月份差
        delta_months = (self.current_month.year - start_date.year) * 12 + (self.current_month.month - start_date.month)
        return max(0, delta_months)

    @property
    def souvenir_count(self):
        """统计收集了多少件精神废料"""
        return len(self.souvenirs_list)

    @property
    def display_coordinates(self):
        """将原始代码翻译成人类可读的北京坐标"""
        from game.constants import DISTRICT_DATA

        # 1. 如果是在校且还没被踢出来 (CUC 特权)
        if self.school_code == '110105' and not self.is_dorm_cleared:
            return "北京市朝阳区 · 定福庄东街1号 (传媒大学宿舍)"

        # 2. 如果正在流浪
        if not self.current_district:
            # 根据学校决定流浪地点
            if self.school_code == '110105':
                return "北京市朝阳区 · 定福庄南门外 (流浪中...)"
            else:
                return "北京市海淀区 · 中关村大街 (五道口桥洞/流浪中)"

        # 3. 如果已经租房
        dist = DISTRICT_DATA.get(self.current_district)
        if dist:
            # 区分北京市内和河北燕郊
            prefix = "河北省廊坊市" if self.current_district == '131082' else "北京市"
            return f"{prefix}{dist['name']} · {dist['vibe']}"

        return "未知坐标 (信号丢失)"

    @property
    def display_location(self):
        """将 1101xx 翻译为具体的北京市行政区划地址"""
        # 1. 如果还在宿舍 (CUC 研一特权)
        if self.school_code == '110105' and not self.is_dorm_cleared:
            return "北京市朝阳区 · 定福庄东街1号 (校内宿舍)"

        # 2. 如果正在流浪 (没有 current_district)
        if not self.current_district:
            if self.school_code == '110105':
                return "北京市朝阳区 · 定福庄南门外 (流浪中)"
            else:
                return "北京市海淀区 · 中关村大街桥洞 (流浪中)"

        # 3. 正常坐标翻译
        location_map = {
            '110108': '北京市海淀区 · 中关村/学院路',
            '110105': '北京市朝阳区 · 定福庄/双桥',

            '110112': '北京市通州区 · 北运河',
            '110114': '北京市昌平区 · 回龙观/天通苑',
            '110113': '北京市顺义区 · 俸伯/石门',
            '131082': '河北省廊坊市 · 燕郊 (跨省中)',
            '110115': '北京市大兴区 · 亦庄',

            '110117': '北京市平谷区',
        }
        return location_map.get(self.current_district, "北京市 · 未知坐标")

    @property
    def risk_resistance(self):
        """计算 🧯 抗风险值 (0-100)"""
        # 1. 财务权重 (占 40%) - 1.5w 为满分标准
        m_score = min(max(self.money / 15000, 0), 1) * 40

        # 2. 身体与理智 (各占 20%)
        hp_max = getattr(self, 'hp_max', 100) or 100  # 防止 None
        h_score = min(max(self.hp / hp_max, 0), 1) * 20
        s_score = min(max(self.san / 100, 0), 1) * 20

        # 3. 学术权重 (占 20%) - CUC 100% 满分，PKU 180% 满分
        goal = 100 if self.school_code == '110105' else 180
        p_score = min(max(self.thesis_progress / goal, 0), 1) * 20

        # 4. 动态修正：流浪状态下抗风险能力减半
        total = m_score + h_score + s_score + p_score
        if self.is_homeless():
            total *= 0.5

        return round(total, 2)


class District(models.Model):
    code = models.CharField(max_length=6)  # 110112 等
    name = models.CharField(max_length=50)
    base_rent = models.IntegerField()
    hp_modifier = models.IntegerField(default=0)  # 区域对体力的影响