# game/views.py
import random
from datetime import timedelta, date
from django.contrib import messages
from django.shortcuts import render, redirect

try:
    import requests
    import json
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

from .models import Player
from .constants import LEISURE_SPOTS, DISTRICT_DATA, MONTHLY_SETTLEMENTS, INTERN_SPOTS
from .logic import process_month_tick, init_player_stats, record_action


def get_current_player():
    return Player.objects.first()

def index(request):
    player = get_current_player()
    return redirect('dashboard') if player else redirect('init_game')

def init_game(request):
    if request.method == 'POST':
        school_code = request.POST.get('school_code')
        from django.contrib.auth.models import User
        user, _ = User.objects.get_or_create(username='Dave')

        Player.objects.filter(user=user).delete()
        player = Player.objects.create(
            user=user,
            school_code=school_code,
            current_month=date(2025, 9, 1)  # 修复从字符串传入导致的 DateField 报错
        )
        init_player_stats(player)
        return redirect('dashboard')
    
    # 读取每个学校的通关次数
    from django.db.models import Count, Q
    cuc_completions = Player.objects.filter(
        school_code='110105',
        ending_type__in=['GRADUATED', 'PHD']
    ).count()

    pku_completions = Player.objects.filter(
        school_code='110108',
        ending_type__in=['GRADUATED', 'PHD']
    ).count()

    # 准备区域数据传递给模板
    from .constants import DISTRICT_DATA, DISTRICT_RENEWAL_CRISIS
    districts_with_info = {}
    
    # 学校坐标（用于计算距离）
    school_coordinates = {
        '110105': {'name': '中国传媒大学', 'lng': 116.549348, 'lat': 39.917044},  # CUC
        '110108': {'name': '北京大学', 'lng': 116.311188, 'lat': 39.992236},  # PKU
    }
    
    # 区域坐标（用于计算距离）
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
    
    for code, district in DISTRICT_DATA.items():
        district_info = district.copy()
        # 检查是否有涨价危机
        crisis = DISTRICT_RENEWAL_CRISIS.get(code)
        if crisis and 'money_mod' in crisis['options'].get('A', {}):
            money_mod = crisis['options']['A']['money_mod']
            district_info['potential_increase'] = f"{int((money_mod - 1) * 100)}%"
            district_info['increased_rent'] = int(district['rent'] * money_mod)
        else:
            district_info['potential_increase'] = "无"
            district_info['increased_rent'] = district['rent']
        
        # 计算到两个学校的预估距离（使用高德地图API）
        district_info['distance_to_schools'] = {}
        for school_code, school_coord in school_coordinates.items():
            if code in district_coordinates:
                district_coord = district_coordinates[code]
                # 调用高德地图API计算距离
                distance_info = calculate_distance_with_amap(
                    district_coord['lng'], district_coord['lat'],
                    school_coord['lng'], school_coord['lat']
                )
                district_info['distance_to_schools'][school_code] = distance_info
        
        districts_with_info[code] = district_info
    
    return render(request, 'game/init_game.html', {
        'districts': districts_with_info,
        'cuc_completions': cuc_completions,
        'pku_completions': pku_completions
    })


def calculate_distance_with_amap(from_lng, from_lat, to_lng, to_lat):
    """使用高德地图API计算两点间的距离和时间"""

    
    # 高德地图API配置
    api_key = "ec7fcd6803b73661f18a80fb095824c5"  # 使用天气API相同的key
    
    # 构建请求URL
    url = "https://restapi.amap.com/v3/distance"
    params = {
        'key': api_key,
        'origins': f"{from_lng},{from_lat}",
        'destination': f"{to_lng},{to_lat}",
        'type': '2'  # 1-直线距离，2-驾车导航距离（实际路程）
    }
    
    try:
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        
        if data['status'] == '1' and data['results']:
            distance = int(data['results'][0]['distance'])  # 距离（米）
            duration = int(data['results'][0]['duration'])   # 时间（秒）
            
            # 转换为更友好的格式
            if distance >= 1000:
                distance_str = f"{distance/1000:.1f}公里"
            else:
                distance_str = f"{distance}米"
            
            if duration >= 3600:
                hours = duration // 3600
                minutes = (duration % 3600) // 60
                duration_str = f"{hours}小时{minutes}分钟"
            elif duration >= 60:
                duration_str = f"{duration//60}分钟"
            else:
                duration_str = f"{duration}秒"
            
            return {
                'distance': distance,
                'duration': duration,
                'distance_str': distance_str,
                'duration_str': duration_str
            }
        else:
            # API调用失败，使用备用计算
            return calculate_distance_fallback(from_lng, from_lat, to_lng, to_lat)
    except Exception as e:
        # 网络错误，使用备用计算
        return calculate_distance_fallback(from_lng, from_lat, to_lng, to_lat)


def calculate_distance_fallback(from_lng, from_lat, to_lng, to_lat):
    """备用距离计算（使用直线距离估算）"""
    import math
    
    # 使用Haversine公式计算直线距离
    R = 6371000  # 地球半径（米）
    
    lat1_rad = math.radians(from_lat)
    lat2_rad = math.radians(to_lat)
    delta_lat = math.radians(to_lat - from_lat)
    delta_lng = math.radians(to_lng - from_lng)
    
    a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    
    distance = R * c  # 直线距离（米）
    
    # 估算通勤时间（假设平均速度30km/h，考虑城市交通）
    estimated_duration = int(distance / 30000 * 3600)  # 秒
    
    # 转换为友好的格式
    if distance >= 1000:
        distance_str = f"{distance/1000:.1f}公里"
    else:
        distance_str = f"{distance:.0f}米"
    
    if estimated_duration >= 3600:
        hours = estimated_duration // 3600
        minutes = (estimated_duration % 3600) // 60
        duration_str = f"约{hours}小时{minutes}分钟"
    elif estimated_duration >= 60:
        duration_str = f"约{estimated_duration//60}分钟"
    else:
        duration_str = f"约{estimated_duration}秒"
    
    return {
        'distance': int(distance),
        'duration': estimated_duration,
        'distance_str': distance_str,
        'duration_str': duration_str
    }


def calculate_dynamic_san_cost(player, spot_id):
    """根据玩家距离动态计算SAN消耗（如八达岭长城）"""
    import math
    
    # 八达岭长城坐标（延庆区）
    BADALING_COORDS = {'lng': 116.017, 'lat': 40.356}
    
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
    
    # 获取玩家当前位置坐标
    if player.current_district and player.current_district in district_coordinates:
        player_coord = district_coordinates[player.current_district]
    else:
        # 默认使用学校坐标
        school_coordinates = {
            '110105': {'lng': 116.549348, 'lat': 39.917044},  # CUC
            '110108': {'lng': 116.311188, 'lat': 39.992236},  # PKU
        }
        player_coord = school_coordinates.get(player.school_code, {'lng': 116.397428, 'lat': 39.90923})
    
    # 计算到八达岭的距离
    R = 6371000  # 地球半径（米）
    
    lat1_rad = math.radians(player_coord['lat'])
    lat2_rad = math.radians(BADALING_COORDS['lat'])
    delta_lat = math.radians(BADALING_COORDS['lat'] - player_coord['lat'])
    delta_lng = math.radians(BADALING_COORDS['lng'] - player_coord['lng'])
    
    a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    
    distance = R * c  # 直线距离（米）
    
    # 根据距离动态计算SAN消耗
    # 基础逻辑：距离越远，SAN消耗越大
    # 0-30km: 20 SAN（近郊）
    # 30-60km: 25 SAN（中等距离）
    # 60-90km: 30 SAN（较远）
    # 90km+: 35 SAN（很远）
    
    if distance <= 30000:  # 30km以内
        san_cost = 20
    elif distance <= 60000:  # 30-60km
        san_cost = 25
    elif distance <= 90000:  # 60-90km
        san_cost = 30
    else:  # 90km以上
        san_cost = 35
    
    return san_cost


def dashboard(request):
    player = get_current_player()
    if not player:
        return redirect('init_game')

    # 检查是否触发致谢环节
    thank_you_response = check_thank_you_moment(request)
    if thank_you_response:
        return thank_you_response

    # --- 🆕 解析已购纪念品详情 ---
    from .constants import LEISURE_SPOTS
    owned_ids = player.souvenirs_list  # 调用 models 里的属性获取 ID 列表
    owned_items = []
    for sid in owned_ids:
        item_data = LEISURE_SPOTS.get(sid)
        if item_data:
            owned_items.append(item_data)

    renewal_data = None
    if getattr(player, 'is_in_renewal_crisis', False):
        from .constants import DISTRICT_RENEWAL_CRISIS
        renewal_data = DISTRICT_RENEWAL_CRISIS.get(player.current_district)

    is_truly_homeless = player.is_homeless()
    if player.school_code == '110105' and not player.is_dorm_cleared:
        is_truly_homeless = False

    if is_truly_homeless:
        messages.warning(request, "⚠️ 你正处于流浪状态！由于缺乏睡眠和安全感，HP 正在大幅下降。")

    if player.school_code == '110105' and player.current_month.year == 2026 and player.current_month.month == 7:
        messages.error(request, "🚨 宿管通知：本月底将进行宿舍清场，请 110105 的同学抓紧寻找住处！")

    if player.is_game_over:
        return render(request, 'game/game_over.html', {'player': player})

    current_month_idx = player.current_month.month
    settlement_data = MONTHLY_SETTLEMENTS.get(current_month_idx, MONTHLY_SETTLEMENTS[1])

    # 🆕 计算当前位置到学校的距离信息
    distance_info = None
    if player.current_district:
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
        
        if player.school_code in school_coordinates and player.current_district in district_coordinates:
            school_coord = school_coordinates[player.school_code]
            district_coord = district_coordinates[player.current_district]
            
            # 计算距离
            distance_info = calculate_distance_with_amap(
                district_coord['lng'], district_coord['lat'],
                school_coord['lng'], school_coord['lat']
            )

    context = {
        'player': player,
        'settlement_data': settlement_data,
        'owned_souvenirs': owned_items,  # 🆕 传给前端
        'renewal_data': renewal_data,
        'risk_resistance': getattr(player, 'risk_resistance', 50),
        'distance_info': distance_info,  # 🆕 距离信息
    }
    return render(request, 'game/dashboard.html', context)


def game_over(request):
    """游戏结束页面：展示 game_over.html，支持直接 URL 访问。"""
    player = get_current_player()
    if not player:
        return redirect('index')
    heartbreaking_quote = get_heartbreaking_quote(player)
    return render(request, 'game/game_over.html', {
        'player': player,
        'heartbreaking_quote': heartbreaking_quote,
    })


def get_heartbreaking_quote(player):
    """根据玩家状态选择终局独白文案。
    
    规则：
    - 顺义毕业（GRADUATED/PHD）：触发专属暖心文案
    - 特殊结局（LAST_MILE_MIRACLE / THORNY_DIPLOMA）：触发专属文案
    - HP死亡（SLAYED_HP）：触发扎心文案（💀骷髅头场景）
    - 其他死亡（学术/钱/SAN）：不触发骷髅文案，返回 None
    """
    from .constants import HEARTBREAKING_QUOTES
    import random

    # ── 顺义毕业专属暖心文案 ──────────────────────────────────────
    if player.ending_type in ('GRADUATED', 'PHD') and player.current_district == '110113':
        return "你走出俸伯站，手里攥着那张沉甸甸的纸。远处顺义机场的飞机划过长空，那一刻你觉得，15 号线不仅通往朝阳，也通往你的未来。"

    # ── 特殊结局文案 ──────────────────────────────────────────────
    if player.ending_type == 'LAST_MILE_MIRACLE':
        return "你在俸伯站的寒风中晕倒，好心的外卖骑手把你送进了顺义区医院。你在病床上用颤抖的手点击了'提交'，那 0.69% 的缺憾被导师手动填补了。"

    if player.ending_type == 'THORNY_DIPLOMA':
        return "虽然你的实验数据还差一组对照，但你凭借满格的理智在答辩现场舌战群儒，导师含泪给你签了字。"

    # ── 正常毕业/其他非HP死亡：不显示骷髅独白 ───────────────────
    if player.ending_type not in ('SLAYED_HP',):
        return None

    # ── 以下仅在 HP 死亡时触发 ────────────────────────────────────
    quotes_pool = []

    # 1. 根据终结坐标
    if player.current_district and player.current_district in HEARTBREAKING_QUOTES:
        quotes_pool.extend(HEARTBREAKING_QUOTES[player.current_district])

    # 2. 高进度低血量
    if player.thesis_progress > 80:
        quotes_pool.extend(HEARTBREAKING_QUOTES.get('high_thesis_low_hp', []))

    # 3. 通用兜底
    quotes_pool.extend(HEARTBREAKING_QUOTES.get('general', []))

    if quotes_pool:
        return random.choice(quotes_pool)

    return "你的代码还能跑，你却跑不动了。"


def final_settlement(request):
    player = get_current_player()
    if not player or not player.is_game_over:
        return redirect('dashboard')

    # Use FinalMLP scoring engine to determine defense outcome
    try:
        from engine.scoring import score_player
        score_result = score_player(player)
        pass_prob = score_result.score
    except Exception:
        # Fallback: simple heuristic based on thesis progress and HP
        grad_thresh = 100.0 if player.school_code == '110105' else 180.0
        pass_prob = min(
            (player.thesis_progress / grad_thresh) * 0.7
            + (player.hp / 100.0) * 0.2
            + (player.san / float(player.san_cap or 100)) * 0.1,
            1.0,
        )

    result = 'PASS' if pass_prob > 0.5 else 'FAIL'

    if result == 'PASS':
        if player.ending_type != 'GRADUATED':
            player.ending_type = 'GRADUATED'
            player.save(update_fields=['ending_type'])
    else:
        if player.ending_type != 'SLAYED_ACADEMIC':
            player.ending_type = 'SLAYED_ACADEMIC'
            player.save(update_fields=['ending_type'])

    result_data = {
        "player": player,
        "result": result,
        "pass_probability": round(pass_prob, 4),
    }

    return render(request, 'game/final_settlement.html', {
        'player': player,
        'result_data': result_data,
    })


def check_thank_you_moment(request):
    """检查是否触发致谢环节"""
    player = get_current_player()
    if not player:
        return None
    
    # 根据学校设置不同的触发条件
    if player.school_code == '110105':  # CUC
        # CUC：论文进度 > 90% 且 SAN < 15
        if player.thesis_progress > 90.0 and player.san < 15.0:
            return render(request, 'game/thank_you_moment.html', {'player': player})
    elif player.school_code == '110108':  # PKU
        # PKU：论文进度 >160 SAN<18
        if player.thesis_progress > 160.0 and player.san < 18.0:
            return render(request, 'game/thank_you_moment.html', {'player': player})
    return None


def thank_you_moment_page(request):
    """致谢环节页面"""
    player = get_current_player()
    if not player:
        return redirect('dashboard')
    
    # 检查触发条件（与 check_thank_you_moment 保持一致）
    if player.school_code == '110105':  # CUC
        # CUC：论文进度 > 90% 且 SAN < 15
        if player.thesis_progress <= 90.0 or player.san >= 15.0:
            return redirect('dashboard')
    elif player.school_code == '110108':  # PKU
        # PKU：论文进度 > 160% 且 SAN < 18
        if player.thesis_progress <= 160.0 or player.san >= 18.0:
            return redirect('dashboard')
    
    return render(request, 'game/thank_you_moment.html', {'player': player})


def thank_you_action(request):
    """执行致谢行动"""
    player = get_current_player()
    if not player:
        return redirect('dashboard')
    
    # 再次检查触发条件（与 check_thank_you_moment 保持一致）
    if player.school_code == '110105':  # CUC
        # CUC：论文进度 > 90% 且 SAN < 15
        if player.thesis_progress <= 90.0 or player.san >= 15.0:
            return redirect('dashboard')
    elif player.school_code == '110108':  # PKU
        # PKU：论文进度 > 160% 且 SAN < 18
        if player.thesis_progress <= 160.0 or player.san >= 18.0:
            return redirect('dashboard')
    
    # 检查余额
    if player.money < 2700:
        messages.error(request, "❌ 余额不足，无法请同门吃饭。")
        return redirect('thank_you_moment')
    
    # 执行致谢行动
    player.money -= 2000+player.money*0.25
    player.san = min(player.san + 20.0, player.san_cap)
    player.save()
    
    messages.success(request, "🎉 你请同门吃了顿好的，大家的鼓励让你瞬间恢复了理智！")
    return redirect('dashboard')


def handle_renewal(request):
    player = get_current_player()
    if request.method == 'POST' and getattr(player, 'is_in_renewal_crisis', False):
        choice_key = request.POST.get('choice')
        from .constants import DISTRICT_RENEWAL_CRISIS
        crisis = DISTRICT_RENEWAL_CRISIS.get(player.current_district)

        if crisis:
            opt = crisis['options'].get(choice_key)
            if opt:
                # 无论选什么，都要应用数值结算 (修复前被无视)
                player.hp = round(player.hp + opt.get('hp', 0), 2)
                player.san = round(player.san + opt.get('san', 0), 2)
                player.thesis_progress = max(0.0, round(player.thesis_progress + opt.get('thesis', 0), 2))

                if opt.get('action') == 'kick_out':
                    player.current_district = None
                    player.rent_contract_end = None
                    player.money = round(player.money + opt.get('money', 0), 2)
                    messages.warning(request, "你卷起铺盖走出了房门，黑夜比论文还冷。")
                else:
                    player.rent_contract_end = player.current_month + timedelta(days=180)
                    player.money = round(player.money + opt.get('money', 0), 2)

                    # 修复租金上浮逻辑：续约时需要支付正常租金 + 上涨部分
                    if 'money_mod' in opt:
                        rent = DISTRICT_DATA[player.current_district]['rent']
                        # 计算6个月的基础租金
                        base_rent_cost = rent * 6
                        # 计算上涨部分的额外成本
                        extra_cost = rent * (opt['money_mod'] - 1) * 6
                        # 总成本 = 基础租金 + 上涨部分
                        total_cost = base_rent_cost + extra_cost
                        player.money = round(player.money - total_cost, 2)
                        messages.warning(request, f"你咬牙支付了 {total_cost:.0f} 元（含基础租金 {base_rent_cost:.0f} 元 + 涨租部分 {extra_cost:.0f} 元）应对接下来半年的续约。")

                    messages.success(request, "合同已续签。")

                player.is_in_renewal_crisis = False
                player.save()
    return redirect('dashboard')


def take_leisure(request, spot_id):
    player = get_current_player()
    from .constants import LEISURE_SPOTS
    spot = LEISURE_SPOTS.get(spot_id)

    if not spot:
        messages.error(request, "❌ 找不到该项目。")
        return redirect('leisure_list')

    # 1. 余额判定
    cost = spot.get('money_cost', 0)
    if player.money < cost:
        messages.error(request, f"💸 余额不足！")
        return redirect('leisure_list')

    # 2. 扣费
    player.money = round(player.money - cost, 2)

    # 3. 核心修复：属性加成应用 (只要有数值就应用)
    # 无论 type 是 activity、leisure 还是 ai，只要定义了增益就加血
    hp_gain = spot.get('hp_gain', 0)
    
    # 🆕 处理动态SAN消耗（如八达岭长城）
    san_cost = spot.get('san_cost', 0)
    if san_cost == 'DYNAMIC':
        # 根据玩家距离动态计算SAN消耗
        san_cost = calculate_dynamic_san_cost(player, spot_id)
    
    san_gain = -san_cost
    thesis_gain = spot.get('thesis_gain', 0)

    if hp_gain or san_gain or thesis_gain:
        player.hp = min(player.hp + hp_gain, 100)
        # SAN 恢复不能超过当前上限
        player.san = min(player.san + san_gain, player.san_cap)
        player.thesis_progress = round(player.thesis_progress + thesis_gain, 2)

    # 4. 判定是否为纪念品 (处理上限提升)
    if spot.get('type') == 'souvenir' or spot.get('is_souvenir'):
        # 🚨 修复：不能修改只读属性，要修改背后的字符串字段
        owned_list = player.souvenirs_list  # 获取当前列表

        if spot_id not in owned_list:
            owned_list.append(spot_id)
            # 将列表转回字符串存入数据库
            player.souvenirs_owned = ",".join(owned_list)

            # 处理上限提升逻辑
            if 'san_cap_boost' in spot:
                player.san_cap += spot['san_cap_boost']
                player.san += spot['san_cap_boost']

            messages.success(request, f"🎁 购入纪念品：{spot['name']}。工位属性提升！")
        else:
            messages.info(request, f"📦 你已经拥有 {spot['name']} 了。")

    record_action(player, spot.get('name', 'Unknown Leisure'))
    player.save()
    messages.success(request, f"✨ {spot['name']} 执行成功。")
    return redirect('leisure_list')


def leisure_list(request):
    player = get_current_player()
    from .constants import LEISURE_SPOTS

    # 🆕 分类提取，确保两个列表都有数据
    activities = {k: v for k, v in LEISURE_SPOTS.items() if v.get('type') in ['leisure', 'activity', 'consumable', 'ai']}
    souvenirs = {k: v for k, v in LEISURE_SPOTS.items() if v.get('is_souvenir') or v.get('type') == 'souvenir'}

    return render(request, 'game/leisure_list.html', {
        'player': player,
        'activities': activities,
        'souvenirs': souvenirs
    })


def study(request):
    player = get_current_player()
    if player.san >= 45 and player.hp >= 20:
        player.san -= 45
        player.hp -= 20
        gain = round(random.uniform(4.0, 8.0), 2)
        player.thesis_progress += gain
        player.save()
        building = '教四' if player.school_code == '110105' else '理科一号楼'
        messages.success(request, f"💻 在{building}肝了一夜代码，论文进度 +{gain}%！")
    else:
        messages.error(request, "❌ 别硬撑了，你的 SAN 或 HP 不足以支撑高强度学术。")
    return redirect('dashboard')


def work_list(request):
    player = get_current_player()
    display_spots =[]
    for key, spot in INTERN_SPOTS.items():
        # 同步修复渲染扣血数值与后端结算匹配逻辑
        hp_drain = spot['hp_drain']
        if player.current_district and player.current_district == spot.get('location'):
            hp_drain *= 0.65
        elif player.current_district and player.current_district != spot.get('location'):
            hp_drain += 15

        spot_info = spot.copy()
        spot_info['id'] = key
        spot_info['total_hp_drain'] = round(hp_drain, 2)
        display_spots.append(spot_info)

    return render(request, 'game/work_list.html', {'player': player, 'spots': display_spots})


def execute_work(request, spot_id):
    player = get_current_player()
    spot = INTERN_SPOTS.get(spot_id)

    r_val = getattr(player, 'risk_resistance', 50)
    efficiency_mod = 1.0 + (r_val / 500)

    salary = spot['salary']
    hp_drain = spot['hp_drain']
    san_cost = spot['san_cost']
    thesis_gain = spot.get('thesis_gain', 0) # 修复此前写错字典 Key 导致增益全军覆没的 Bug

    # 修复获取 location，触发职住平衡 Buff
    if player.current_district and player.current_district == spot.get('location'):
        hp_drain *= 0.65
        san_cost -= 10
        messages.info(request, "🏠 职住平衡 Buff：你住得离工位很近，通勤非常优雅。")
    elif player.current_district and player.current_district != spot.get('location'):
        hp_drain += 15
        messages.warning(request, "🚇 跨区远征：漫长的换乘正在压榨你的身体。")

    if player.school_code == spot.get('preferred_school'):
        salary *= 1.25
        san_cost *= 0.8
        messages.success(request, f"🎓 学缘溢价：因为你的母校背景，你获得了更高的劳务费。")

    # 🆕 前期课程负担：CUC前3个月，PKU前5个月实习收益80%
    months_elapsed = player.survival_months
    course_burden_months = 3 if player.school_code == '110105' else 5  # CUC:3个月，PKU:5个月
    
    if months_elapsed < course_burden_months:
        salary *= 0.8
        messages.warning(request, f"📚 前期课程负担：还有{course_burden_months - months_elapsed}个月才能全力实习，收益80%。")

    san_cost = max(5, san_cost - (r_val / 10))

    if player.hp <= hp_drain:
        messages.error(request, "❌ 你的身体已到极限，无法支持高强度的卷王生活。")
        return redirect('dashboard')

    if player.san < san_cost:
        messages.error(request, "❌ 看着电脑屏幕，你突然想大笑并格式化硬盘。你已无法工作。")
        return redirect('dashboard')

    player.money = round(player.money + (salary * efficiency_mod), 2)
    player.hp = round(player.hp - hp_drain, 2)
    player.san = round(player.san - san_cost, 2)
    player.thesis_progress = round(player.thesis_progress + thesis_gain, 2)


    if spot.get('provides_housing', False) and player.is_homeless():
        player.temp_housing_active = True
        messages.success(request, "🏢 航司/企业为你提供了简易宿舍，你告别了本月的风餐露宿。")

    player.save()
    return redirect('dashboard')


def process_settlement(request):
    player = get_current_player()
    if request.method == 'POST' and player:
        choice_key = request.POST.get('settlement_choice')
        month_key = player.current_month.month
        settlement_data = MONTHLY_SETTLEMENTS.get(month_key, MONTHLY_SETTLEMENTS[1])

        if settlement_data and 'options' in settlement_data:
            opt = settlement_data['options'].get(choice_key)
            if opt:
                # 🆕 斩杀线机制：钱少于3000时按数值扣钱，否则按百分比扣钱
                money_change = opt.get('money', 0)
                if money_change < 0:  # 只对扣钱的情况应用斩杀线
                    if player.money < 3000:
                        # 钱少于3000，按数值扣钱，但确保不会变成负数
                        deduction = abs(money_change)
                        player.money = round(max(0, player.money - deduction), 2)
                    else:
                        # 钱多于3000，按百分比扣钱（百分比基于原数值）
                        # 计算百分比：假设原数值是基于一定基数的百分比
                        # 例如：-1500 对应 3% 的扣钱比例
                        percentage = abs(money_change) / 50000  # 将数值转换为百分比
                        actual_deduction = player.money * percentage
                        player.money = round(max(0, player.money - actual_deduction), 2)
                else:
                    # 正数变化（赚钱），直接加钱
                    player.money = round(player.money + money_change*random.randint(2,8), 2)
                
                player.hp = round(player.hp + opt.get('hp', 0), 2)
                player.san = round(player.san + opt.get('san', 0), 2)
                player.thesis_progress = max(0.0, round(player.thesis_progress + opt.get('thesis', 0), 2))
                player.save()

        success = process_month_tick(player)

        if not success:
            messages.warning(request, "⚠️ 租约已到期！房东正在敲门，请处理续约事宜。")
            return redirect('dashboard')
        else:
            # 【修复重点 2】：这里如果判定游戏结束，不应该再跳回 dashboard，直接去 game_over
            if player.is_game_over:
                if player.ending_type == 'PHD':
                    messages.success(request, "🎉 恭喜！你成功申请了硕博连读，不需要再担心住宿问题了！")
                elif player.ending_type == 'GRADUATED':
                    messages.success(request, "🎓 恭喜！你顺利毕业了！")
                elif player.ending_type == 'SLAYED_ACADEMIC':
                    messages.error(request, "💀 论文进度不足，未能通过答辩...")
                elif player.ending_type == 'SLAYED_HP':
                    messages.error(request, "💀 身体不堪重负，倒在了求学路上...")
                elif player.ending_type == 'SLAYED_MONEY':
                    messages.error(request, "💀 债务缠身，被迫退学...")
                elif player.ending_type == 'SANHE_MASTER':
                    messages.error(request, "💀 理智归零，成为了三河大神...")
                else:
                    messages.error(request, "💀 终局已至。")
                return redirect('game_over')
            else:
                # 🆕 检查是否获得科研经费Buff
                if player.thesis_progress >= 128.0 and not player.has_research_fund:
                    player.has_research_fund = True
                    player.save()
                    messages.success(request, "🎉 恭喜！你的论文进度达到128%，获得了导师的科研经费支持！")
                
                messages.success(request, f"📅 熬过了清算，新的一月开始了：{player.current_month:%Y年%m月}。")

    return redirect('dashboard')


def npc_market(request):
    player = get_current_player()
    seed_val = player.current_month.year * 100 + player.current_month.month
    rng = random.Random(seed_val)

    water_guide_quotes =[
        "“延毕那是老实人的事，这篇 YOLO 改进综述，5000 块带走，进度直接 +20%。”",
        "“我看你骨骼惊奇，这有个魔改 Transformer 插件，5000 块，包你 SOTA。”",
        "“实验跑不通？别急，水导这里有‘必中版’种子，5000 块，进度飞起。”",
        "“想读博吗？先把这篇综述买了，5000 块，咱们师徒一场，不坑你。”",
        "“这篇论文太水了？水导这里有个‘强化版’代码，5000 块，直接让你的结果翻倍。”"
        "硕士哪有什么科研道德可言？这篇论文买了，5000 块，直接让你在答辩时吓死评委！"
    ]

    npcs =[
        {
            'name': '水导',
            'msg': rng.choice(water_guide_quotes),
            'action': 'water_guide_deal'
        },
        {
            'name': '蜻蜓队长',
            'msg': f'“北京奥，都得有点东西。这碗豆汁儿，干了它，你就忘了在 {getattr(player, "current_district", "此地")} 的烦恼。”',
            'action': 'drink_douzhir'
        }
    ]
    return render(request, 'game/market.html', {'npcs': npcs, 'player': player})


def drink_douzhir(request):
    player = get_current_player()
    if player.money >= 500:
        if player.san < 40:
             messages.error(request, "❌ 你看着绿油油的豆汁，理智告诉你绝对不能喝。")
             return redirect('dashboard')
        player.money -= 500
        player.hp = min(100.0, player.hp + 15)
        player.san -= 40
        player.save()
        messages.success(request, "呕...干了蜻蜓队长的豆汁。胃在翻滚，但脑子里已经不想论文了。")
    return redirect('dashboard')


def water_guide_deal(request):
    player = get_current_player()
    if player.money >= 5000:
        if player.san < 30:
            messages.error(request, "❌ 你的理智太低，无法理解水导发来的高深莫测的代码。")
            return redirect('dashboard')

        player.money -= 5000
        player.thesis_progress += 20.0
        player.san -= 30

        modern_deals =[
            "💸 转账成功。水导发来了一个『QWEN3.5_LORA_256K.zip』，RAG 检索准确率暴增！",
            "💸 水导利用私人关系给了你一个『8卡 H100 集群』的白嫖权限，LoRA 训练速度飞起！",
            "💸 水导丢给你一份『2025年 RecSys 顶会 SOTA 源码』，虽然没注释，但效果远超！",
            "💸 水导帮你解决了 CUDA OOM 报错，原来是 KV Cache 策略写挂了。进度拉满！"
        ]
        deal_msg = random.choice(modern_deals)
        player.save()
        messages.success(request, f"{deal_msg} 进度 +20%。")

    else:
        # 修复了无 F-String 前缀造成的语法隐患
        fail_quotes =[
            "“没钱？这点 Slot 算力你都租不起，还想跑 70B 的参数？”",
            "“没钱？水导冷笑一声：‘科研不是慈善，建议你去西二旗多搬两个月砖。’”",
            f"“没钱？水导摇了摇头：‘看来你只能继续在 {getattr(player, 'current_district', '这儿')} 过苦日子了。’”"
        ]
        messages.error(request, f"❌ {random.choice(fail_quotes)}")

    return redirect('dashboard')


def move_house(request):
    player = get_current_player()
    if player.has_moved_this_month:
        messages.warning(request, "❌ 你本月已经搬过一次家了，精力耗尽，无法再次折腾。")
        return redirect('dashboard')

    message = "北京奥，都得有点东西。没房，你就没东西。"
    if player.money < 5000:
        message = "水导说：‘没钱租房？来我这水篇论文挣点外快吧。’"

    return render(request, 'game/move_house.html', {'player': player, 'districts': DISTRICT_DATA, 'captain_msg': message})


def select_district(request, district_code):
    player = get_current_player()
    district = DISTRICT_DATA.get(district_code)

    rent = district['rent']
    signing_cost = rent * 5

    if player.money >= signing_cost:
        player.money -= signing_cost
        player.current_district = district_code
        player.deposit_held = rent

        player.rent_contract_end = player.current_month + timedelta(days=180)
        player.has_moved_this_month = True

        district_name = district.get('name', 'Unknown')
        record_action(player, f'Move to {district_name}')
        player.save()

        messages.success(request, f"合同已签署！有效期至 {player.rent_contract_end:%Y-%m}。押金已存入中介账户。")
    else:
        messages.error(request, "🤡 余额不足。海淀的房东不相信眼泪，只相信『押一付三』。")

    return redirect('dashboard')




def quick_rest(request):
    player = get_current_player()
    if request.method == 'POST':
        # 🆕 流浪状态时扣HP和2倍SAN值
        if player.is_homeless():
            player.hp = max(0.0, player.hp - 15.0)  # 流浪状态扣HP
            player.san = min(player.san - 50.0, player.san_cap)  # 流浪状态扣2倍SAN（25*2）
            messages.warning(request, "😰 在街头躺平，没有宿舍的庇护，身心俱疲...")
        else:
            player.hp = min(player.hp + 15.0, 100.0)  # 正常状态恢复HP
            player.san = min(player.san - 25.0, player.san_cap)  # 正常状态扣SAN
            messages.info(request, "🛏️ 你在宿舍床上躺平了整个周末，但命暂时保住了。")
        
        # 防止进度变负数
        player.thesis_progress = max(0.0, player.thesis_progress - 5.0)
        player.save()

    return redirect('dashboard')
