# 北京研究生生存模拟器

一个基于真实北京地理的研究生生存模拟游戏。扮演中传或北大研究生，在北京的房租、通勤、论文、精神压力中挣扎求生。

## 游戏截图

<!-- TODO: 添加截图 -->

## 游戏特点

- **真实北京地理**: 8个行政区 + 燕郊，基于真实坐标计算通勤距离
- **双校选择**: 中传(2年制/有宿舍) vs 北大(3年制/无宿舍)
- **四大属性**: 💰钱、❤️体力、🧠理智、🎓论文进度
- **随机事件**: 每月遭遇各种扎心事件
- **多结局**: 毕业、猝死、欠债、三河大神等 8 种结局

## 快速开始

### 环境要求

- Python 3.10+
- pip

### 安装步骤

```bash
# 克隆仓库
git clone https://github.com/YANS311/Survival110112.git
cd Survival110112

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt

# 数据库迁移
python manage.py migrate

# 创建管理员(可选)
python manage.py createsuperuser

# 启动服务器
python manage.py runserver
```

访问 http://127.0.0.1:8000 开始游戏。

### 生产部署

```bash
# 设置环境变量
export DJANGO_SECRET_KEY='your-secret-key'
export DJANGO_DEBUG=0
export DJANGO_ALLOWED_HOSTS='your-domain.com'

# 使用 uvicorn 启动
uvicorn core.asgi:application --host 0.0.0.0 --port 8000 --workers 2
```

## 游戏机制

### 通勤系统

根据学校和居住地的直线距离，动态计算体力消耗：

| 距离 | 体力消耗 |
|------|----------|
| <5km | 0 |
| 5-15km | 0 ~ -5 |
| 15-30km | -5 ~ -10 |
| >30km | -10 ~ -15 |

### 主线事件: CUC 宿舍清退

选择中传后，你将在研二享有宿舍特权。但 2026 年 7 月，学校将强制清退宿舍，你需要提前做好准备。

## 技术栈

- Django 5.2
- django-ninja (API)
- SQLite (开发) / PostgreSQL (生产)
- Uvicorn (ASGI)

## License

MIT
