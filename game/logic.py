# game/logic.py
import random
from datetime import timedelta, date
from .constants import (DISTRICT_DATA, SCHOOL_POLICIES, SCHOOL_DISTRICT_RELATION,
                        DEFAULT_COMMUTE, DORM_EVICTION_MAIN_QUEST)


def calculate_living_buffs(player):
    """动态 Buff 计算"""
    # 1. 宿舍特权判定必须放在第一位，防止中传学生被判定为流浪状态
    if player.school_code == '110105' and not player.is_dorm_cleared:
        return {
            'thesis_mult': 1.1,
            'san_drain': 2,
            'hp_recovery': 0
        }

    # 2. 流浪状态判定 (兼容因实习触发的航司包住逻辑)
    if player.is_homeless() and not getattr(player, 'temp_housing_active', False):
        return {
            'thesis_mult': 0.5,
            'san_drain': 15,
            'hp_recovery': -5
        }

    # 临时包住增益
    if player.is_homeless() and getattr(player, 'temp_housing_active', False):
        return {
            'thesis_mult': 0.8,
            'san_drain': 5,
            'hp_recovery': 0
        }

    # 3. 租房状态：查询 SCHOOL_DISTRICT_RELATION
    relation_key = (player.school_code, player.current_district)
    relation = SCHOOL_DISTRICT_RELATION.get(relation_key, DEFAULT_COMMUTE)
    
    # 🆕 动态计算通勤体力消耗（基于距离），不再使用常量
    hp_recovery = 0
    if player.current_district:
        # 根据距离动态调整体力消耗
        hp_recovery = calculate_dynamic_hp_consumption(player.school_code, player.current_district)

    return {
        'thesis_mult': relation['thesis_mult'],
        'san_drain': 5,
        'hp_recovery': hp_recovery
    }


def record_action(player, action_name: str, max_history=10):
    """Appends an action to the player's history, keeping it to a max length."""
    history = player.action_history.split(',') if player.action_history else []
    history.append(action_name)

    # Keep the list at the desired max length
    if len(history) > max_history:
        history = history[-max_history:]

    player.action_history = ",".join(filter(None, history))
    # Note: player.save() should be called in the view after this function.


def calculate_dynamic_hp_consumption(school_code, district_code):
    """根据距离动态计算体力消耗"""
    import math
    
    # 学校坐标
    school_coordinates = {
        '110105': {'lng': 116.549348, 'lat': 39.917044},  # CUC
        '110108': {'lng': 116.311188, 'lat': 39.992236},  # PKU
    }
    
    # 区域坐标
    district_coordinates = {
        '110108': {'lng': 116.311188, 'lat': 39.992236},  # 海淀
        '110105': {'lng': 116.549348, 'lat': 39.917044},  # 朝阳
        '110112': {'lng': 116.656435, 'lat': 39.902645},  # 通州
        '110114': {'lng': 116.326222, 'lat': 40.078594},  # 昌平
        '110113': {'lng': 116.653519, 'lat': 40.123456},  # 顺义
        '131082': {'lng': 116.813822, 'lat': 39.953632},  # 燕郊
        '110115': {'lng': 116.493519, 'lat': 39.723456},  # 亦庄
        '110117': {'lng': 117.123456, 'lat': 40.123456},  # 平谷
    }
    
    if school_code not in school_coordinates or district_code not in district_coordinates:
        # 如果坐标缺失，使用默认值
        default_values = {
            '110105': 10, '110108': 10, '110112': 5, '110114': -8,
            '110113': -2, '131082': -16, '110115': -8, '110117': -12
        }
        return default_values.get(district_code, -5)
    
    school_coord = school_coordinates[school_code]
    district_coord = district_coordinates[district_code]
    
    # 使用Haversine公式计算直线距离
    R = 6371000  # 地球半径（米）
    
    lat1_rad = math.radians(school_coord['lat'])
    lat2_rad = math.radians(district_coord['lat'])
    delta_lat = math.radians(district_coord['lat'] - school_coord['lat'])
    delta_lng = math.radians(district_coord['lng'] - school_coord['lng'])
    
    a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    
    distance = R * c  # 直线距离（米）
    
    # 根据距离动态计算体力消耗（降低消耗，避免玩家宁可流浪）
    # 基础逻辑：距离越远，体力消耗越大（负值越大）
    # 0-5km: 0
    # 5-15km: 0 到 -5
    # 15-30km: -5 到 -10
    # 30km+: -10 到 -15
    
    if distance <= 5000:  # 5km以内
        hp_consumption = 0  # 不扣体力
    elif distance <= 15000:  # 5-15km
        hp_consumption = -int((distance - 5000) / 2000)  # 每1公里-1
    elif distance <= 30000:  # 15-30km
        hp_consumption = -3 - int((distance - 15000) / 5000) # 每5公里-1
    else:  # 30km以上
        hp_consumption = -10 - int((distance - 30000) / 5000) # 每5公里-1
        hp_consumption = max(hp_consumption, -15)  # 最大消耗-15
    
    return hp_consumption


def process_month_tick(player):
    """逻辑心脏：处理跨月所有数值"""
    # 【修复重点】：如果进来时就已经触发死亡判定，必须把死亡状态保存到数据库中！
    if check_game_status(player):
        player.save()  # 必须加上这一行！
        return True

    # 租约到期拦截
    if player.current_district and player.rent_contract_end:
        if player.current_month >= player.rent_contract_end:
            if not getattr(player, 'is_in_renewal_crisis', False):
                player.is_in_renewal_crisis = True
                player.save()
                return False
            # 🆕 修复：如果已经处于续约危机状态，不再重复触发，继续正常跨月流程

    # 🆕 CUC 宿舍清退主线事件检查
    if player.school_code == '110105' and not player.is_dorm_cleared:
        dorm_quest_result = check_dorm_eviction_quest(player)
        if dorm_quest_result:
            player.save()
            return False  # 暂停跨月，等待玩家选择

    player.has_moved_this_month = False
    player.san_cap = getattr(player, 'next_month_san_cap', 100)
    player.next_month_san_cap = 100

    if player.school_code == '110105':
        if player.current_month >= date(2026, 8, 1):
            player.is_dorm_cleared = True

    buffs = calculate_living_buffs(player)

    player.san = round(player.san - buffs.get('san_drain', 0), 2)
    player.hp = round(player.hp + buffs.get('hp_recovery', 0), 2)

    policy = SCHOOL_POLICIES[player.school_code]
    rent = 0

    # 精确判断真实流浪：有宿舍或者临时住处时不扣 20 血
    is_truly_homeless = player.is_homeless()
    if player.school_code == '110105' and not player.is_dorm_cleared:
        is_truly_homeless = False

    if is_truly_homeless and not getattr(player, 'temp_housing_active', False):
        player.hp = round(player.hp - 20, 2)
    else:
        if player.school_code == '110105' and not player.is_dorm_cleared:
            rent = policy['dorm_cost']
        elif player.current_district:
            rent = DISTRICT_DATA[player.current_district]['rent']

    # 🆕 导师的科研经费补助
    research_fund_bonus = 0
    if player.has_research_fund and player.thesis_progress > 100.0:
        # CUC打4折
        base_bonus = 2500
        if player.school_code == '110105':
            research_fund_bonus = base_bonus * 0.4  # 1000元
        else:
            research_fund_bonus = base_bonus  # 2500元

    player.money = round(player.money + getattr(player, 'monthly_allowance', 0) - rent + research_fund_bonus, 2)

    player.san = round(player.san + 100, 2)
    if player.san > player.san_cap:
        player.san = float(player.san_cap)

    # 🆕 触发动态事件
    from .events import DynamicEventManager
    event_manager = DynamicEventManager()
    event_result = event_manager.trigger_event(player, player.current_month)
    if event_result:
        # 事件已触发，保存到 player 上供视图层读取
        player._last_event = event_result

    # 🆕 检查挖矿被抓概率
    if getattr(player, 'gpu_mining_active', False):
        detection_rate = getattr(player, 'mining_detection_rate', 0)
        if random.random() < detection_rate:
            player.ending_type = 'ACADEMIC_FRAUD'
            player.is_game_over = True
            player.gpu_mining_active = False
            player.save()
            return True
        # 每月增加 15% 被抓概率
        player.mining_detection_rate = min(detection_rate + 0.15, 1.0)
        player.money += 800  # 挖矿收入

    curr = player.current_month
    if curr.month == 12:
        player.current_month = date(curr.year + 1, 1, 1)
    else:
        player.current_month = date(curr.year, curr.month + 1, 1)

    # 跨月后清空上月获取的包住状态
    player.temp_housing_active = False

    check_game_status(player)
    player.save()
    return True


def init_player_stats(player):
    if player.school_code == '110105':
        player.money = 20000.0
        player.is_dorm_cleared = False
    elif player.school_code == '110108':
        player.money = 1e5
        player.is_dorm_cleared = True

    player.hp = 100
    player.san = 100
    player.thesis_progress = 0.0
    player.save()


def check_game_status(player):
    r_val = getattr(player, 'risk_resistance', 50)

    if player.hp <= 0:
        # 🆕 顺义/俸伯特供结局：最后一公里的奇迹
        if (player.current_district == '110113' and  # 顺义
            player.money > 3000 and
            player.thesis_progress >= 95.0):
            player.is_game_over = True
            player.ending_type = 'LAST_MILE_MIRACLE'
            return True
        
        # 原有的保底机制
        if r_val > 75 and player.money > 3000:
            player.hp = 15.0
            player.money -= 3000
            return False
        player.is_game_over = True
        player.ending_type = 'SLAYED_HP'
        return True

    # 修复此前因为随意 return False 导致无敌免死的 Bug
    if player.money < -6000:
        credit_limit = -6000 - (r_val * 100)
        if player.money < credit_limit:
            player.is_game_over = True
            player.ending_type = 'SLAYED_MONEY'
            return True

    if player.san < 0:
        player.is_game_over = True
        player.ending_type = 'SANHE_MASTER'
        return True

    # 🆕 中期答辩检查
    # CUC（110105）：第二年12月（2026年12月）中期答辩，要求50进度
    # PKU（110108）：第三年12月（2027年12月）中期答辩，要求100进度
    if player.school_code == '110105':
        # CUC两年制：2026年12月中期答辩
        if player.current_month.year == 2026 and player.current_month.month == 12:
            if player.thesis_progress < 50:
                player.is_game_over = True
                player.ending_type = 'SLAYED_ACADEMIC'
                return True
    elif player.school_code == '110108':
        # PKU三年制：2027年12月中期答辩
        if player.current_month.year == 2027 and player.current_month.month == 12:
            if player.thesis_progress < 100:
                player.is_game_over = True
                player.ending_type = 'SLAYED_ACADEMIC'
                return True

    # 毕业答辩检查
    grad_year = 2027 if player.school_code == '110105' else 2028
    if player.current_month.year >= grad_year and player.current_month.month >= 6:
        threshold = 100.0 if player.school_code == '110105' else 180.0
        phd_threshold = 180.0 if player.school_code == '110105' else 220.0

        # 🆕 学术韧性判定：带刺的毕业证
        if (player.thesis_progress >= 95.0 and 
            player.thesis_progress < threshold and
            player.san >= 80.0):
            # 论文达到95%以上但未达标，且SAN值极高，触发带刺的毕业证
            player.is_game_over = True
            player.ending_type = 'THORNY_DIPLOMA'
            return True

        if player.thesis_progress >= phd_threshold:
            player.ending_type = 'PHD'
        elif player.thesis_progress >= threshold:
            player.ending_type = 'GRADUATED'
        else:
            player.ending_type = 'SLAYED_ACADEMIC'

        player.is_game_over = True
        return True

    return False


# ═══════════════════════════════════════════════════════════════════════════════
# 🆕 CUC 宿舍清退主线事件
# ═══════════════════════════════════════════════════════════════════════════════

def check_dorm_eviction_quest(player):
    """
    检查是否触发宿舍清退主线事件。
    返回事件数据如果需要暂停跨月，返回 None 如果无需暂停。
    """
    current = player.current_month
    quest = DORM_EVICTION_MAIN_QUEST

    # 遍历三个阶段
    for i, phase in enumerate(quest['phases']):
        phase_month = date(current.year, phase['month'][1], 1)
        phase_key = f'dorm_eviction_phase_{i+1}_done'

        # 检查当前月份是否匹配，且该阶段未完成
        if current.year == phase['month'][0] and current.month == phase['month'][1]:
            if not getattr(player, phase_key, False):
                return {
                    'type': 'dorm_eviction',
                    'phase': i + 1,
                    'title': phase['title'],
                    'desc': phase['desc'],
                    'options': phase['options']
                }

    # 第四阶段：如果到了 2026 年 8 月还没搬，强制清退
    if current.year == 2026 and current.month >= 8:
        if not player.is_dorm_cleared:
            # 检查是否已经处理过强制清退
            if not getattr(player, 'dorm_eviction_forced_done', False):
                return {
                    'type': 'dorm_eviction',
                    'phase': 4,
                    'title': quest['phase_4']['title'],
                    'desc': quest['phase_4']['desc'],
                    'options': {}  # 无选项，直接强制执行
                }

    return None


def process_dorm_eviction_choice(player, phase, choice):
    """
    处理宿舍清退主线事件的玩家选择。
    phase: 阶段 (1-4)
    choice: 选项 ('A', 'B', 'C')
    """
    quest = DORM_EVICTION_MAIN_QUEST

    if phase == 4:
        # 强制清退阶段，无选择
        player.is_dorm_cleared = True
        player.current_district = None  # 流浪
        player.san = max(0, player.san - 30)
        player.hp = max(0, player.hp - 20)
        player.dorm_eviction_forced_done = True
        player.save()
        return {'success': True, 'msg': '你被强制清退，现在是街头流浪状态。'}

    # 获取对应阶段的选项
    phase_data = quest['phases'][phase - 1]
    if choice not in phase_data['options']:
        return {'success': False, 'msg': '无效选项'}

    option = phase_data['options'][choice]

    # 应用数值变化
    if 'money' in option:
        player.money = round(player.money + option['money'], 2)
    if 'san' in option:
        player.san = round(player.san + option['san'], 2)
    if 'hp' in option:
        player.hp = round(player.hp + option['hp'], 2)
    if 'thesis' in option:
        player.thesis_progress = round(player.thesis_progress + option['thesis'], 2)

    # 设置标记
    if 'flag' in option:
        setattr(player, option['flag'], True)
    if 'action' in option:
        # 处理特殊动作
        action = option['action']
        if action == 'dorm_eviction_normal':
            player.is_dorm_cleared = True
            # 如果已经租房，自动入住
            if not player.current_district and getattr(player, 'dorm_eviction_rented', False):
                player.current_district = '110112'  # 默认通州
        elif action == 'dorm_eviction_delay_3days':
            # 延期 3 天，设置一个标记让下个月再检查
            player.dorm_eviction_delayed = True
        elif action == 'dorm_eviction_forced':
            player.is_dorm_cleared = True
            player.current_district = None
            player.san = max(0, player.san - 20)

    # 标记该阶段完成
    setattr(player, f'dorm_eviction_phase_{phase}_done', True)
    player.save()

    return {
        'success': True,
        'msg': option['desc'],
        'flag': option.get('flag'),
        'action': option.get('action')
    }
