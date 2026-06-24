# game/urls.py
from django.urls import path

from game import views

urlpatterns = [
    path('', views.index, name='index'),
    path('init/', views.init_game, name='init_game'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('final_settlement/', views.final_settlement, name='final_settlement'),  # 🆕 结算页专属路由
    path('game_over/', views.game_over, name='game_over'),  # 游戏结束页面

    # 核心动作
    path('study/', views.study, name='study'),
    path('work/', views.work_list, name='work_list'),
    path('work/execute/<str:spot_id>/', views.execute_work, name='execute_work'),
    path('leisure/', views.leisure_list, name='leisure_list'),  # 🆕 找回解压选项
    path('leisure/take/<str:spot_id>/', views.take_leisure, name='take_leisure'),
    path('rest/', views.quick_rest, name='quick_rest'),  # 🆕 宿舍躺平(低保)

    # 住房与续约
    path('move/', views.move_house, name='move_house'),
    path('select_district/<str:district_code>/', views.select_district, name='select_district'),
    path('handle_renewal/', views.handle_renewal, name='handle_renewal'),

    # 黑市与清算
    path('market/', views.npc_market, name='npc_market'),
    path('market/water_guide/', views.water_guide_deal, name='water_guide_deal'),
    path('market/douzhir/', views.drink_douzhir, name='drink_douzhir'),
    path('settlement/', views.process_settlement, name='process_settlement'),

    # 致谢环节
    path('thank_you_moment/', views.thank_you_moment_page, name='thank_you_moment'),
    path('thank_you_action/', views.thank_you_action, name='thank_you_action'),

    # 🆕 生存挣扎机制
    path('survival_struggle/', views.handle_survival_struggle, name='handle_survival_struggle'),
]
