# 一级PE在线项目工作台（Render 在线版）

这是一个**公开只读 + 管理员可刷新**的一级 PE 在线工作台：

- 公开访客：直接打开网址即可查看最近一次成功结果
- 管理员：登录后可修改研究范围、保存一次 API Key、点击“立即更新”
- 服务端：使用 OpenAI Responses API + Web Search（如果你的代理兼容 `/v1/responses` 也可直接替换）
- 数据持久化：保存到 Render Persistent Disk（`/var/data`）

## 你会得到什么

- 一个固定公网网址
- 首页直接展示：今日优先赛道、最终推荐、候选公司池、横向比较、解释型评分引擎、公开证据宇宙
- 管理后台可做：
  - 修改赛道库 / 任务说明 / 阶段偏好 / 排除项
  - 一次性保存 API Key（加密后写到服务器磁盘）
  - 点击“立即更新”触发当天公开信息搜索
  - 切回内置样例，防止答辩现场翻车

---

## 一、最适合你的部署方式（小白版）

### 步骤 1：把这个文件夹上传到 GitHub

新建一个仓库，例如 `pe-online-workbench`，把当前目录全部上传。

### 步骤 2：在 Render 用 Blueprint 部署

1. 登录 Render
2. 点击 **New → Blueprint**
3. 连接你的 GitHub 仓库
4. 选择这个仓库
5. Render 会读取根目录下的 `render.yaml`
6. 在创建时，Render 会要求你填写：
   - `ADMIN_PASSWORD`
   - `OPENAI_API_KEY`

> 如果你暂时不想在 Render 面板里填 `OPENAI_API_KEY`，也可以先留空；部署完成后，用管理员密码登录后台，在“管理员控制台”里保存一次 API Key。

### 步骤 3：等待部署完成

成功后，Render 会给你一个 `onrender.com` 网址。

### 步骤 4：打开网址

- 公共页：谁都能看
- 管理员：点击右上角“管理员登录”

---

## 二、部署后第一次怎么用

### 1. 先登录管理员

密码就是你在 Render 里设置的 `ADMIN_PASSWORD`。

### 2. 检查 API Key 来源

登录后右侧控制台会显示：

- Key 来源：`env` 表示来自 Render 环境变量
- Key 来源：`encrypted_store` 表示来自你在后台保存的一次性 Key

### 3. 点“立即更新”

系统会：

1. 读取你的研究范围和排除条件
2. 调用 OpenAI Responses API
3. 使用 Web Search 搜索当天公开信息
4. 输出赛道、候选池、横向比较、排除逻辑、解释型评分和最终推荐
5. 将结果缓存到服务器磁盘

### 4. 公开页自动变成最新结果

答辩时默认先展示最新缓存结果；你也可以现场再点一次“立即更新”。

---

## 三、适合答辩演示的使用建议

### 最稳打法

答辩前一晚先登录后台点一次“立即更新”。

现场演示时：

1. 打开公网网址
2. 先讲公开页上已经生成好的结果
3. 如网络允许，再登录后台点击“立即更新”
4. 如果实时更新慢，公开页也不会空白，因为始终保留“最近一次成功结果”

### 一键防翻车

管理员后台提供 **“恢复为内置样例”**。如果现场网络不好，可以立刻切回样例。

---

## 四、你可以改哪些配置

管理员后台支持修改：

- 研究范围 / 赛道库
- 投资任务说明
- 阶段偏好
- 地域
- 候选公司数量
- 模型名
- 允许搜索的域名
- OpenAI / 代理 Responses 地址
- 排除方向
- 排除公司
- 公开页说明
- 一次性保存 API Key

如果你有自己的 OpenAI 兼容代理，只要它兼容 `/v1/responses`，把“OpenAI / 代理 Responses 地址”改成你的代理地址即可。

---

## 五、如果你不想在 Render 面板里填 OPENAI_API_KEY

可以这样：

1. 部署时先只填 `ADMIN_PASSWORD`
2. 部署完成后打开网址
3. 管理员登录
4. 在控制台输入一次 API Key
5. 点“保存设置”

这会把 API Key 加密后存到服务器磁盘。

---

## 六、本地运行（可选）

```bash
python -m venv .venv
source .venv/bin/activate   # Windows 用 .venv\Scripts\activate
pip install -r requirements.txt
export ADMIN_PASSWORD=你的密码
export OPENAI_API_KEY=你的Key
python app.py
```

然后打开：

```text
http://127.0.0.1:10000/
```

---

## 七、文件说明

- `app.py`：Flask 后端
- `render.yaml`：Render Blueprint 配置
- `requirements.txt`：依赖
- `.python-version`：Python 版本
- `templates/index.html`：前端页面
- `static/app.js`：交互逻辑
- `static/style.css`：样式
- `data/seed_report.json`：内置样例

---

## 八、上线后建议改的两个地方

1. 把 `name: pe-online-workbench` 改成你喜欢的服务名
2. 在 Render 控制台给服务绑定一个更好记的自定义域名（如果你需要）
